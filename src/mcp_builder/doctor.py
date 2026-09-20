"""Diagnose MCP Builder prerequisites without printing credentials or response bodies."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx

from mcp_builder.corpus.manifest import verify_sources
from mcp_builder.search.store import verify_bundle

CheckStatus = Literal["ok", "degraded", "unready", "skipped"]


@dataclass(frozen=True)
class Check:
    """Represent one sanitized diagnostic result."""

    name: str
    status: CheckStatus
    summary: str
    details: dict[str, object] = field(default_factory=dict)
    next_action: str | None = None


def _read_manifest(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    return manifest


def _check_corpus(root: Path) -> tuple[Check, dict | None]:
    if not root.is_dir() or not (root / "manifest.json").is_file():
        return Check(
            "corpus",
            "unready",
            "The documentation corpus is missing.",
            {"path": str(root)},
            "Run bash scripts/sync-docs.sh, or pass --docs-dir to an existing bundle.",
        ), None
    try:
        manifest = _read_manifest(root)
        if manifest.get("kind") == "sources":
            manifest = verify_sources(root)
        elif manifest.get("kind") == "indexed":
            manifest = verify_bundle(root)
        else:
            raise ValueError("Unsupported corpus kind")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        sqlite3.Error,
    ) as exc:
        return Check(
            "corpus",
            "unready",
            "The documentation corpus failed integrity validation.",
            {"path": str(root), "error_type": type(exc).__name__},
            "Regenerate the documentation bundle and rerun the doctor.",
        ), None
    return Check(
        "corpus",
        "ok",
        "The local documentation corpus is complete and readable.",
        {
            "path": str(root),
            "kind": manifest["kind"],
            "documents": len(manifest["documents"]),
        },
    ), manifest


def _check_index(root: Path, manifest: dict | None) -> Check:
    if manifest is None:
        return Check("index", "skipped", "Index validation was skipped because the corpus failed.")
    if manifest.get("kind") == "sources":
        return Check(
            "index",
            "skipped",
            "The source snapshot is valid; its immutable index is built in the Docker image.",
        )
    index_path = root / "index.sqlite"
    try:
        database = sqlite3.connect(index_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
            passages = database.execute("SELECT count(*) FROM passages").fetchone()[0]
        finally:
            database.close()
        if integrity != "ok" or passages < 1:
            raise ValueError("Invalid lexical index")
        if manifest.get("passages") not in {None, passages}:
            raise ValueError("Passage count does not match the manifest")
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return Check(
            "index",
            "unready",
            "The lexical search index is invalid.",
            {"error_type": type(exc).__name__},
            "Rebuild the MCP Builder image from the verified source snapshot.",
        )
    return Check(
        "index",
        "ok",
        "The lexical search index passed its integrity check.",
        {"passages": passages},
    )


def _run_command(command: list[str], *, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _check_docker(root: Path, timeout: float) -> Check:
    executable = shutil.which("docker")
    if executable is None:
        return Check(
            "docker",
            "unready",
            "Docker is not installed or is not on PATH.",
            next_action="Install Docker, or use the local uv workflow.",
        )
    try:
        result = _run_command(
            [executable, "version", "--format", "{{.Server.Version}}"],
            cwd=root,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(
            "docker",
            "unready",
            "The Docker engine could not be reached.",
            {"error_type": type(exc).__name__},
            "Start Docker and rerun the doctor.",
        )
    if result.returncode != 0 or not result.stdout.strip():
        return Check(
            "docker",
            "unready",
            "The Docker CLI is present but its engine is unavailable.",
            {"exit_code": result.returncode},
            "Start Docker and rerun the doctor.",
        )
    return Check(
        "docker",
        "ok",
        "The Docker engine is available.",
        {"server_version": result.stdout.strip().splitlines()[0][:64]},
    )


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _health_url(host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    return f"http://{rendered_host}:{port}/health"


def _configured_bind(root: Path, environment: dict[str, str]) -> str:
    """Resolve only Compose's public bind key without loading or exposing other .env data."""
    configured = environment.get("MCP_BIND_IP", "").strip()
    if configured:
        return configured
    env_file = root / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "127.0.0.1"
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "MCP_BIND_IP":
            return value.strip().strip('"\'') or "127.0.0.1"
    return "127.0.0.1"


def _check_port(host: str, port: int, timeout: float) -> Check:
    if not _is_loopback(host):
        return Check(
            "port",
            "unready",
            "A non-loopback bind is forbidden because this service has no authentication.",
            {"host": host, "port": port},
            "Use 127.0.0.1 (or ::1) and place any authenticated remote gateway separately.",
        )
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.get(_health_url(host, port))
        if response.status_code in {200, 503}:
            try:
                health_status = response.json().get("status")
            except (ValueError, AttributeError):
                health_status = None
            if health_status in {"ok", "degraded", "unready"}:
                return Check(
                    "port",
                    health_status,
                    (
                        "MCP Builder is already listening on the configured loopback port."
                        if health_status != "unready"
                        else "MCP Builder is listening but its health endpoint is unready."
                    ),
                    {"host": host, "port": port, "health": health_status},
                    (
                        "Inspect docker compose logs mcp-builder before using the connection."
                        if health_status == "unready"
                        else None
                    ),
                )
    except httpx.HTTPError:
        pass
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        return Check(
            "port",
            "unready",
            "The configured loopback port is occupied by an unexpected service.",
            {"host": host, "port": port, "error_type": type(exc).__name__},
            "Stop the conflicting service or choose another MCP_PORT.",
        )
    finally:
        probe.close()
    return Check(
        "port",
        "ok",
        "The configured loopback port is available.",
        {"host": host, "port": port},
    )


def _api_key(environment: dict[str, str]) -> str | None:
    direct = environment.get("OPENAI_API_KEY", "").strip()
    if direct:
        return direct
    secret_file = environment.get("OPENAI_API_KEY_FILE", "").strip()
    if not secret_file:
        return None
    try:
        return Path(secret_file).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _check_embedding(environment: dict[str, str], timeout: float) -> Check:
    base_url = environment.get("OPENAI_BASE_URL", "").rstrip("/")
    if not base_url:
        return Check(
            "embedding",
            "skipped",
            "Semantic search is optional and is not configured; lexical search remains available.",
        )
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or not parsed.path.endswith("/v1")
    ):
        return Check(
            "embedding",
            "degraded",
            "OPENAI_BASE_URL is invalid; it must be an HTTP(S) /v1 URL without credentials.",
            next_action="Correct OPENAI_BASE_URL or unset it to use lexical-only mode.",
        )
    key = _api_key(environment)
    if key is None:
        return Check(
            "embedding",
            "degraded",
            "The embedding endpoint is configured but its credential is unavailable.",
            next_action="Provide OPENAI_API_KEY or a readable OPENAI_API_KEY_FILE.",
        )
    model = environment.get("EMBEDDING_MODEL", "bge-m3").strip()
    try:
        with httpx.Client(
            base_url=base_url + "/",
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
            trust_env=False,
        ) as client:
            response = client.post(
                "embeddings",
                json={"model": model, "input": ["MCP Builder connectivity probe"]},
            )
        if response.is_error:
            return Check(
                "embedding",
                "degraded",
                "The configured embedding endpoint rejected the connectivity probe.",
                {"http_status": response.status_code, "model": model},
                "Check the endpoint, model, and secret without placing the secret in configuration.",
            )
    except httpx.HTTPError as exc:
        return Check(
            "embedding",
            "degraded",
            "The configured embedding endpoint is unreachable.",
            {"error_type": type(exc).__name__, "model": model},
            "Start the endpoint or unset OPENAI_BASE_URL to use lexical-only mode.",
        )
    return Check(
        "embedding",
        "ok",
        "The optional embedding endpoint accepted a probe.",
        {"model": model},
    )


def _valid_opencode_profiles(root: Path) -> bool:
    try:
        v1 = json.loads((root / "integrations/opencode/v1/opencode.json").read_text("utf-8"))
        v2 = json.loads((root / "integrations/opencode/v2/opencode.json").read_text("utf-8"))
        v1_server = v1["mcp"]["mcp_builder"]
        v2_server = v2["mcp"]["servers"]["mcp_builder"]
        agents = [
            root / "integrations/opencode/v1/.opencode/agents/mcp-companion.md",
            root / "integrations/opencode/v2/.opencode/agents/mcp-companion.md",
        ]
        frontmatters = [path.read_text("utf-8").split("---", 2)[1] for path in agents]
        return (
            v1["default_agent"] == "mcp-companion"
            and v1_server["url"] == "http://127.0.0.1:8000/mcp"
            and v1_server["oauth"] is False
            and isinstance(v1_server["timeout"], int)
            and v2["default_agent"] == "mcp-companion"
            and v2_server["url"] == "http://127.0.0.1:8000/mcp"
            and v2_server["oauth"] is False
            and v2_server["protocol"] == "auto"
            and v2_server["codemode"] is True
            and all("model:" not in item and "permission" not in item for item in frontmatters)
        )
    except (OSError, IndexError, KeyError, TypeError, json.JSONDecodeError):
        return False


def _version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", text)
    return tuple(map(int, match.groups())) if match else None


def _check_opencode(root: Path, timeout: float) -> Check:
    if not _valid_opencode_profiles(root):
        return Check(
            "opencode",
            "unready",
            "The bundled OpenCode V1/V2 profiles are missing or invalid.",
            next_action="Restore integrations/opencode and rerun the doctor.",
        )
    executable = shutil.which("opencode")
    if executable is None:
        return Check(
            "opencode",
            "unready",
            "The OpenCode profiles are valid, but the OpenCode CLI is not on PATH.",
            {"profiles": ["v1", "v2"]},
            "Install OpenCode 1.18.31 or newer, then copy the matching profile.",
        )
    try:
        version_result = _run_command([executable, "--version"], cwd=root, timeout=timeout)
        parsed_version = _version(version_result.stdout + version_result.stderr)
        list_result = _run_command([executable, "mcp", "list"], cwd=root, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(
            "opencode",
            "unready",
            "OpenCode could not complete its local diagnostic commands.",
            {"error_type": type(exc).__name__},
            "Run opencode --version and opencode mcp list manually.",
        )
    if version_result.returncode != 0 or parsed_version is None:
        return Check(
            "opencode",
            "unready",
            "The OpenCode CLI version could not be determined.",
            {"exit_code": version_result.returncode},
            "Verify the OpenCode installation.",
        )
    rendered_version = ".".join(map(str, parsed_version))
    if parsed_version < (1, 18, 31):
        return Check(
            "opencode",
            "unready",
            "OpenCode is older than the tested 1.18.31 baseline.",
            {"version": rendered_version},
            "Upgrade OpenCode or validate the integration manually.",
        )
    clean_output = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", list_result.stdout)
    server_lines = [line.lower() for line in clean_output.splitlines() if "mcp_builder" in line]
    configured = list_result.returncode == 0 and bool(server_lines)
    if not configured:
        return Check(
            "opencode",
            "unready",
            "OpenCode is compatible, but mcp_builder is not active in this project.",
            {"version": rendered_version, "profiles": ["v1", "v2"]},
            "Copy the matching profile into the target project and run opencode mcp list.",
        )
    if not any("connected" in line and "failed" not in line for line in server_lines):
        return Check(
            "opencode",
            "unready",
            "OpenCode has mcp_builder configured, but the connection is not healthy.",
            {"version": rendered_version},
            "Start MCP Builder, then rerun opencode mcp list and the doctor.",
        )
    return Check(
        "opencode",
        "ok",
        "OpenCode is compatible and reports the mcp_builder connection.",
        {"version": rendered_version},
    )


def run_doctor(
    root: Path,
    *,
    docs_dir: Path | None = None,
    host: str | None = None,
    port: int = 8000,
    timeout: float = 3.0,
    environment: dict[str, str] | None = None,
) -> dict:
    """Run sanitized local checks and return one deterministic report."""
    root = root.resolve()
    environment = dict(os.environ if environment is None else environment)
    host = host or _configured_bind(root, environment)
    corpus_root = (docs_dir or Path(environment.get("DOCS_DIR", root / "documentation"))).resolve()
    corpus, manifest = _check_corpus(corpus_root)
    checks = [
        corpus,
        _check_index(corpus_root, manifest),
        _check_docker(root, timeout),
        _check_port(host, port, timeout),
        _check_embedding(environment, timeout),
        _check_opencode(root, timeout),
    ]
    if any(check.status == "unready" for check in checks):
        status = "unready"
    elif any(check.status == "degraded" for check in checks):
        status = "degraded"
    else:
        status = "ok"
    return {
        "schema_version": 1,
        "status": status,
        "checks": [asdict(check) for check in checks],
        "next_actions": [check.next_action for check in checks if check.next_action],
    }


def _render_human(report: dict) -> str:
    labels = {"ok": "OK", "degraded": "WARN", "unready": "FAIL", "skipped": "SKIP"}
    lines = [f"MCP Builder doctor: {report['status'].upper()}"]
    lines.extend(
        f"[{labels[check['status']]}] {check['name']}: {check['summary']}"
        for check in report["checks"]
    )
    if report["next_actions"]:
        lines.append("Next actions:")
        lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines)


def main(arguments: list[str] | None = None) -> int:
    """Run the doctor command and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--docs-dir", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8000")))
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(arguments)
    if not 1 <= args.port <= 65535 or args.timeout <= 0:
        parser.error("--port and --timeout must be positive and valid")
    report = run_doctor(
        args.root,
        docs_dir=args.docs_dir,
        host=args.host,
        port=args.port,
        timeout=args.timeout,
    )
    print(json.dumps(report, indent=2) if args.as_json else _render_human(report))
    return 2 if report["status"] == "unready" else 0


def entrypoint() -> int:
    """Dispatch the installed ``mcp-builder`` command without breaking server startup."""
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        return main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help"}:
        print("usage: mcp-builder [doctor [OPTIONS]]\n\nNo command starts the HTTP server.")
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        del sys.argv[1]
    from mcp_builder.server import main as serve

    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
