"""Tests for the safe local MCP Builder doctor."""

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

from mcp_builder import doctor


def _write_source_corpus(root: Path) -> None:
    files = {
        "indexes/fastmcp.txt": "# FastMCP\n",
        "indexes/mcp.txt": "# MCP\n",
        "docs/fastmcp/start.md": "# Start\n",
        "docs/mcp/spec.md": "# Spec\n",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    manifest = {
        "schema": 1,
        "kind": "sources",
        "complete": True,
        "sources": {"fastmcp": {}, "mcp": {}},
        "documents": [
            {
                "id": "fastmcp:start",
                "path": "docs/fastmcp/start.md",
                "source": "fastmcp",
                "version": "test",
            },
            {
                "id": "mcp:spec",
                "path": "docs/mcp/spec.md",
                "source": "mcp",
                "version": "test",
            },
        ],
        "files": {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in files.items()
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_source_corpus_is_verified_and_index_is_explicitly_build_time(tmp_path):
    """A valid source snapshot is ready even though its index belongs in the image."""
    _write_source_corpus(tmp_path)

    corpus, manifest = doctor._check_corpus(tmp_path)
    index = doctor._check_index(tmp_path, manifest)

    assert corpus.status == "ok"
    assert corpus.details["documents"] == 2
    assert index.status == "skipped"
    assert "Docker image" in index.summary


def test_index_check_opens_sqlite_read_only_and_counts_passages(tmp_path):
    """An indexed runtime bundle must have a coherent non-empty FTS database."""
    database = sqlite3.connect(tmp_path / "index.sqlite")
    database.execute("CREATE TABLE passages (id INTEGER PRIMARY KEY, content TEXT)")
    database.execute("INSERT INTO passages VALUES (0, 'example')")
    database.commit()
    database.close()

    result = doctor._check_index(tmp_path, {"kind": "indexed", "passages": 1})

    assert result.status == "ok"
    assert result.details == {"passages": 1}


def test_indexed_corpus_verifies_every_manifest_hash(tmp_path):
    """Doctor and runtime reject the same corrupted immutable bundle."""
    document = tmp_path / "docs/start.md"
    document.parent.mkdir(parents=True)
    document.write_text("# Start\n", encoding="utf-8")
    database_path = tmp_path / "index.sqlite"
    database = sqlite3.connect(database_path)
    database.execute(
        "CREATE TABLE passages (id INTEGER PRIMARY KEY, content TEXT)"
    )
    database.execute("INSERT INTO passages VALUES (0, 'example')")
    database.commit()
    database.close()
    manifest = {
        "schema": 1,
        "kind": "indexed",
        "complete": True,
        "search": {"lexical": True, "semantic": False},
        "model": None,
        "dimensions": 0,
        "passages": 1,
        "documents": [{"id": "start", "path": "docs/start.md"}],
        "files": {
            "docs/start.md": hashlib.sha256(document.read_bytes()).hexdigest(),
            "index.sqlite": hashlib.sha256(database_path.read_bytes()).hexdigest(),
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    document.write_text("tampered\n", encoding="utf-8")

    corpus, parsed = doctor._check_corpus(tmp_path)

    assert corpus.status == "unready"
    assert parsed is None


def test_non_loopback_bind_is_rejected_before_any_network_probe():
    """The doctor mirrors the runtime guard while HTTP authentication is absent."""
    result = doctor._check_port("0.0.0.0", 8000, 0.1)

    assert result.status == "unready"
    assert "no authentication" in result.summary


def test_compose_bind_is_read_from_dotenv_without_loading_other_values(tmp_path):
    """Doctor sees Compose's effective bind while keeping unrelated secrets opaque."""
    (tmp_path / ".env").write_text(
        "SECRET=do-not-read\nMCP_BIND_IP=0.0.0.0\n",
        encoding="utf-8",
    )

    assert doctor._configured_bind(tmp_path, {}) == "0.0.0.0"
    assert doctor._configured_bind(tmp_path, {"MCP_BIND_IP": "127.0.0.1"}) == "127.0.0.1"


def test_health_503_is_reported_as_builder_unready(monkeypatch):
    """A loading Builder is identified from its JSON body even with HTTP 503."""
    class Response:
        status_code = 503

        @staticmethod
        def json():
            return {"status": "unready"}

    class Client:
        def __init__(self, **kwargs):
            del kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            del args

        @staticmethod
        def get(url):
            del url
            return Response()

    monkeypatch.setattr(doctor.httpx, "Client", Client)

    result = doctor._check_port("127.0.0.1", 8000, 0.1)

    assert result.status == "unready"
    assert result.details["health"] == "unready"


def test_optional_embedding_is_skipped_and_secrets_are_never_rendered():
    """Lexical mode is valid, and malformed credential-bearing URLs stay private."""
    skipped = doctor._check_embedding({}, 0.1)
    secret = "never-print-this"
    invalid = doctor._check_embedding(
        {
            "OPENAI_BASE_URL": f"http://user:{secret}@127.0.0.1:11434/v1",
            "OPENAI_API_KEY": secret,
        },
        0.1,
    )

    assert skipped.status == "skipped"
    assert invalid.status == "degraded"
    assert secret not in json.dumps({"summary": invalid.summary, "details": invalid.details})


def test_bundled_opencode_profiles_cover_v1_and_v2():
    """Both schemas select the primary companion without fixing model or permissions."""
    root = Path(__file__).parents[1]
    assert doctor._valid_opencode_profiles(root)

    v1 = json.loads((root / "integrations/opencode/v1/opencode.json").read_text("utf-8"))
    v2 = json.loads((root / "integrations/opencode/v2/opencode.json").read_text("utf-8"))
    assert v1["default_agent"] == "mcp-companion"
    assert v1["mcp"]["mcp_builder"] == {
        "type": "remote",
        "url": "http://127.0.0.1:8000/mcp",
        "enabled": True,
        "oauth": False,
        "timeout": 30000,
    }
    assert v2["mcp"]["servers"]["mcp_builder"]["protocol"] == "auto"
    assert v2["mcp"]["servers"]["mcp_builder"]["codemode"] is True
    for version in ("v1", "v2"):
        agent = (
            root / f"integrations/opencode/{version}/.opencode/agents/mcp-companion.md"
        ).read_text("utf-8")
        frontmatter = agent.split("---", 2)[1]
        assert "model:" not in frontmatter
        assert "permission" not in frontmatter


def test_opencode_check_requires_a_connected_server(monkeypatch):
    """Merely listing a failed server is not reported as a healthy connection."""
    root = Path(__file__).parents[1]
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "opencode")

    def run(command, **kwargs):
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "1.18.31\n", "")
        return subprocess.CompletedProcess(command, 0, "x mcp_builder failed\n", "")

    monkeypatch.setattr(doctor, "_run_command", run)

    result = doctor._check_opencode(root, 0.1)

    assert result.status == "unready"
    assert "not healthy" in result.summary


def test_compose_is_loopback_first_and_semantic_search_is_opt_in():
    """The default stack needs no endpoint or secret and carries the runtime bind guard."""
    root = Path(__file__).parents[1]
    base = (root / "compose.yaml").read_text("utf-8")
    semantic = (root / "compose.semantic.yaml").read_text("utf-8")

    assert "${MCP_BIND_IP:-127.0.0.1}:${MCP_PORT:-8000}:8000" in base
    assert "MCP_PUBLIC_BIND_IP: ${MCP_BIND_IP:-127.0.0.1}" in base
    assert "OPENAI_BASE_URL" not in base
    assert 'ENABLE_SEMANTIC: "0"' in base
    assert 'ENABLE_SEMANTIC: "1"' in semantic
    assert "OPENAI_API_KEY_FILE: /run/secrets/openai_api_key" in semantic


def test_report_aggregation_preserves_distinct_operational_states(monkeypatch, tmp_path):
    """A required failure wins over optional degradation and skipped capabilities."""
    monkeypatch.setattr(
        doctor,
        "_check_corpus",
        lambda root: (doctor.Check("corpus", "unready", "broken"), None),
    )
    monkeypatch.setattr(
        doctor,
        "_check_index",
        lambda root, manifest: doctor.Check("index", "skipped", "skipped"),
    )
    monkeypatch.setattr(
        doctor,
        "_check_docker",
        lambda root, timeout: doctor.Check("docker", "degraded", "offline"),
    )
    monkeypatch.setattr(
        doctor,
        "_check_port",
        lambda host, port, timeout: doctor.Check("port", "ok", "free"),
    )
    monkeypatch.setattr(
        doctor,
        "_check_embedding",
        lambda environment, timeout: doctor.Check("embedding", "skipped", "optional"),
    )
    monkeypatch.setattr(
        doctor,
        "_check_opencode",
        lambda root, timeout: doctor.Check("opencode", "ok", "configured"),
    )

    report = doctor.run_doctor(tmp_path, environment={})

    assert report["status"] == "unready"
    assert [item["status"] for item in report["checks"]] == [
        "unready",
        "skipped",
        "degraded",
        "ok",
        "skipped",
        "ok",
    ]


def test_json_cli_returns_nonzero_only_for_unready(monkeypatch, capsys, tmp_path):
    """Automation receives stable JSON and a failing code for blockers."""
    report = {"schema_version": 1, "status": "unready", "checks": [], "next_actions": []}
    monkeypatch.setattr(doctor, "run_doctor", lambda *args, **kwargs: report)

    exit_code = doctor.main(["--root", str(tmp_path), "--json"])
    rendered = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert rendered == report
