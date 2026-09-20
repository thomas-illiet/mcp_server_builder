"""Generate complete example projects and verify them through real toolchains."""

from __future__ import annotations

import argparse
import inspect
import os
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from mcp_builder.projects import generate_project, validate_project


def _mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError("Expected a dictionary-compatible validation result")


def _validate(files: list[dict]) -> dict:
    parameters = inspect.signature(validate_project).parameters
    result = validate_project(files, profile="strict") if "profile" in parameters else validate_project(files)
    return _mapping(result)


def _write_files(root: Path, files: list[dict]) -> None:
    for item in files:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root.resolve()) or target == root.resolve():
            raise ValueError(f"Generated path escapes the project: {item['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8", newline="\n")


def _run(command: list[str], cwd: Path) -> None:
    print(f"[{cwd.name}] $ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _project_python(project: Path) -> Path:
    """Return the locked project's interpreter without spawning a lingering uv wrapper."""
    relative = Path(".venv/Scripts/python.exe") if os.name == "nt" else Path(".venv/bin/python")
    interpreter = project / relative
    if not interpreter.is_file():
        raise RuntimeError(f"Generated project interpreter was not installed: {interpreter}")
    return interpreter


def _wait_for_port(process: subprocess.Popen, port: int, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"Generated HTTP server exited early:\n{output[-4000:]}")
        with socket.socket() as probe:
            probe.settimeout(0.25)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError("Generated HTTP server did not listen within 30 seconds")


@contextmanager
def _http_server(project: Path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = os.environ.copy()
    environment.update({
        "MCP_LISTEN_HOST": "127.0.0.1",
        "MCP_PUBLIC_BIND_IP": "127.0.0.1",
        "MCP_PORT": str(port),
    })
    process = subprocess.Popen(
        [str(_project_python(project)), "-m", "app.server"],
        cwd=project,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    try:
        _wait_for_port(process, port)
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()


def _verify_http(project: Path) -> None:
    with _http_server(project) as port:
        program = f"""import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:{port}/mcp") as client:
        tools = await client.list_tools()
        assert "add" in {{tool.name for tool in tools}}
        result = await client.call_tool("add", {{"a": 20, "b": 22}})
        assert result.data == 42

asyncio.run(main())
"""
        _run([str(_project_python(project)), "-c", program], project)


def _verify_stdio(project: Path) -> None:
    program = """import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

async def main():
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "app.server"],
        cwd=str(Path.cwd()),
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        assert "add" in {tool.name for tool in tools}
        result = await client.call_tool("add", {"a": 20, "b": 22})
        assert result.data == 42

asyncio.run(main())
"""
    _run([str(_project_python(project)), "-c", program], project)


def _exercise(root: Path, template: str, transport: str, verify_http: bool) -> None:
    name = f"generated_{template}"
    result = generate_project(name, template, transport)
    report = _validate(result["files"])
    if not report.get("valid", False) or not report.get("ready", False):
        codes = [item.get("code") for item in report.get("readiness_issues", [])]
        raise RuntimeError(
            f"Generated {template} project is not statically ready: {codes}"
        )
    project = root / name
    project.mkdir()
    _write_files(project, result["files"])
    _run(["uv", "lock"], project)
    _run(["uv", "sync", "--locked"], project)
    _run(["uv", "run", "--locked", "ruff", "check", "."], project)
    _run(["uv", "run", "--locked", "pytest", "-q"], project)
    if transport == "http" and verify_http:
        _verify_http(project)
    elif transport == "stdio":
        _verify_stdio(project)
    print(f"[{name}] generated project verified", flush=True)


def main(arguments: list[str] | None = None) -> int:
    """Generate selected templates and fail at the first real verification error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", choices=["all", "minimal", "structured"], default="all")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--skip-http", action="store_true", help="Skip only the real HTTP call")
    parser.add_argument("--output", type=Path, help="Keep projects in a new empty directory")
    args = parser.parse_args(arguments)
    if shutil.which("uv") is None:
        raise RuntimeError("uv is required to test a generated project")
    templates = ["minimal", "structured"] if args.template == "all" else [args.template]
    if args.output:
        root = args.output.resolve()
        root.mkdir(parents=True, exist_ok=False)
        for template in templates:
            _exercise(root, template, args.transport, not args.skip_http)
    else:
        with tempfile.TemporaryDirectory(prefix="mcp-builder-generated-") as directory:
            for template in templates:
                _exercise(Path(directory), template, args.transport, not args.skip_http)
    if args.transport == "http" and args.skip_http:
        print("All generated projects passed lock, lint, and in-process MCP tests; HTTP skipped.")
    else:
        print("All generated projects passed lock, lint, tests, discovery, and invocation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
