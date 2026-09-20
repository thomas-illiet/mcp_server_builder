"""Return deterministic project files; never write or execute them."""

import keyword
import re

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

from .examples import EXAMPLES
from .guide import GUIDE


def list_templates() -> list[dict]:
    """Return supported templates, parameters and the tested FastMCP version."""
    return [
        {
            "name": name,
            "description": description,
            "parameters": {
                "name": "Python identifier",
                "transport": ["http", "stdio"],
            },
            "fastmcp_version": FASTMCP_VERSION,
        }
        for name, description in (
            (
                "structured",
                "Separate modules for tools, resources, and prompts (recommended)",
            ),
            (
                "minimal",
                "One functional tool with component packages ready for later additions",
            ),
        )
    ]


def _compose(transport: str) -> str:
    """Return a hardened local Compose service for the selected transport."""
    port = '    ports:\n      - "127.0.0.1:8000:8000"\n' if transport == "http" else ""
    environment = (
        "    environment:\n"
        "      MCP_LISTEN_HOST: 0.0.0.0\n"
        "      MCP_PUBLIC_BIND_IP: 127.0.0.1\n"
        if transport == "http" else ""
    )
    stdio = "    stdin_open: true\n" if transport == "stdio" else ""
    return f'''services:
  server:
    build:
      context: .
    init: true
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp:size=64m,mode=1777
{port}{environment}{stdio}    restart: "no"
'''


def _server(transport: str) -> str:
    """Return the shared registration and transport entry point."""
    if transport == "http":
        imports = '''import ipaddress
import os

from app import prompts, resources, tools  # noqa: F401
from app.instance import mcp'''
        guard = '''def _listen_host() -> str:
    """Reject unauthenticated non-loopback publication before starting HTTP."""
    host = os.getenv("MCP_LISTEN_HOST", "127.0.0.1")
    public = os.getenv("MCP_PUBLIC_BIND_IP", host)
    if public.lower() != "localhost":
        try:
            address = ipaddress.ip_address(public.strip("[]"))
        except ValueError as exc:
            raise RuntimeError("MCP_PUBLIC_BIND_IP must be loopback") from exc
        if not address.is_loopback:
            raise RuntimeError("Non-loopback publication requires server authentication")
    return host
'''
        run = (
            'mcp.run(transport="http", host=_listen_host(), '
            'port=int(os.getenv("MCP_PORT", "8000")))'
        )
        prelude = f"{imports}\n\n\n{guard.rstrip()}"
    else:
        imports = '''from app import prompts, resources, tools  # noqa: F401
from app.instance import mcp'''
        run = 'mcp.run(transport="stdio")'
        prelude = imports
    return f'''"""Register components and start the selected transport when run."""

{prelude}

if __name__ == "__main__":
    {run}
'''


def _dockerfile(transport: str) -> str:
    """Return a locked non-root image with an HTTP health probe when applicable."""
    healthcheck = (
        "HEALTHCHECK --interval=10s --timeout=3s --start-period=10s "
        "CMD python -c \"import socket; "
        "connection = socket.create_connection(('127.0.0.1', 8000), 2); "
        "connection.close()\"\n"
        if transport == "http" else ""
    )
    return f'''FROM python:3.14.6-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /uvx /usr/local/bin/
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    UV_PYTHON_DOWNLOADS=never \\
    MCP_LISTEN_HOST=0.0.0.0 \\
    MCP_PUBLIC_BIND_IP=127.0.0.1 \\
    PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
RUN uv sync --locked --no-dev --no-editable
USER 10001:10001
EXPOSE 8000
{healthcheck}CMD ["python", "-m", "app.server"]
'''


def _smoke_test(structured: bool) -> str:
    """Return a discovery and invocation smoke test with real assertions."""
    additional = '''
        resources = await client.list_resources()
        prompts = await client.list_prompts()
        assert "config://version" in {str(item.uri) for item in resources}
        assert "explain" in {item.name for item in prompts}
        assert await client.read_resource("config://version")
        assert await client.get_prompt("explain", {"topic": "MCP"})
''' if structured else ""
    return f'''"""Smoke-test MCP discovery and invocation through an in-process client."""

import pytest
from fastmcp import Client

from app.server import mcp


@pytest.mark.asyncio
async def test_server_discovery_and_invocation():
    """Discover the generated primitives and invoke their functional examples."""
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "add" in {{item.name for item in tools}}
        result = await client.call_tool("add", {{"a": 2, "b": 3}})
        assert result.data == 5
{additional}'''


def generate_project(name: str, template: str = "structured", transport: str = "http") -> dict:
    """Return deterministic project files without writing or executing code.

    Both templates use ``app.instance`` and explicit component packages, so a
    generated tool, resource, or prompt can be added later without changing the
    server architecture. Invalid choices raise ``ValueError``.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or keyword.iskeyword(name):
        raise ValueError("Name must be a lowercase Python identifier, 1 to 64 characters")
    if template not in {"minimal", "structured"} or transport not in {"http", "stdio"}:
        raise ValueError("Unknown template or transport")

    files = {
        "app/__init__.py": '"""FastMCP application package."""\n',
        "app/instance.py": (
            '"""Expose the one shared MCP instance used by every component."""\n\n'
            f'from fastmcp import FastMCP\n\nmcp = FastMCP("{name}")\n'
        ),
        "app/server.py": _server(transport),
        "app/tools/__init__.py": (
            '"""Register tool modules explicitly."""\n\nfrom . import add as add\n'
        ),
        "app/tools/add.py": (
            '"""Register the functional example tool."""\n\n'
            "from app.instance import mcp\n\n\n" + EXAMPLES["tool"][1]
        ),
        "app/resources/__init__.py": '"""Register resource modules explicitly."""\n',
        "app/prompts/__init__.py": '"""Register prompt modules explicitly."""\n',
        "pyproject.toml": f'''[build-system]
requires = ["hatchling==1.32.0"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastmcp=={FASTMCP_VERSION}"]

[dependency-groups]
dev = ["pytest==9.1.1", "pytest-asyncio==1.4.0", "ruff==0.16.6"]

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"
''',
        "Dockerfile": _dockerfile(transport),
        "compose.yaml": _compose(transport),
        ".dockerignore": ".venv\n__pycache__\n.git\n.pytest_cache\n.ruff_cache\n",
        ".gitignore": ".venv/\n__pycache__/\n.pytest_cache/\n.ruff_cache/\n.env\n",
        ".env.example": (
            "# Copy to .env only when the application needs server-side configuration.\n"
            "# Never expose secrets as MCP tool arguments or commit the resulting .env file.\n"
        ),
        "AGENTS.md": f'''# Development instructions

- Target FastMCP {FASTMCP_VERSION} and Python 3.12 or later.
- Keep one shared instance in `app.instance` and register component modules explicitly.
- Keep one public MCP component per module in its matching package.
- Never pass secrets through MCP arguments, results, or logs.
- Replace every generated `TODO` with business logic and meaningful assertions.
- Before reporting completion, run `uv lock`, `uv sync --locked`,
  `uv run --locked ruff check .`, and `uv run --locked pytest`.
- Verify discovery and invocation with the in-process FastMCP client and the configured transport.
''',
        "MCP_BUILDER_GUIDE.md": GUIDE,
        "tests/test_server.py": EXAMPLES["testing"][1],
        "tests/test_smoke.py": _smoke_test(template == "structured"),
    }

    if template == "structured":
        for package, module, topic in (
            ("resources", "version", "resource"),
            ("prompts", "explain", "prompt"),
        ):
            files[f"app/{package}/__init__.py"] = (
                f'"""Register {topic} modules explicitly."""\n\n'
                f"from . import {module} as {module}\n"
            )
            files[f"app/{package}/{module}.py"] = (
                f'"""Register the example {topic} on the shared MCP instance."""\n\n'
                "from app.instance import mcp\n\n\n" + EXAMPLES[topic][1]
            )
        files["tests/test_server.py"] += '''

@pytest.mark.asyncio
async def test_resources_and_prompts():
    """Check invocation of the version resource and explanation prompt."""
    async with Client(mcp) as client:
        assert await client.read_resource("config://version")
        assert await client.get_prompt("explain", {"topic": "MCP"})
'''

    endpoint = (
        "Endpoint: http://127.0.0.1:8000/mcp"
        if transport == "http"
        else "Configure the client to run `python -m app.server` from this directory."
    )
    docker_run = "-p 127.0.0.1:8000:8000" if transport == "http" else "-i"
    files["README.md"] = f'''# {name}

FastMCP {FASTMCP_VERSION} server using the {transport} transport.

Read [MCP_BUILDER_GUIDE.md](MCP_BUILDER_GUIDE.md) and [AGENTS.md](AGENTS.md)
before changing a component.

```bash
uv lock
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest
uv run --locked python -m app.server
```

{endpoint}

```bash
docker compose up --build
# Equivalent direct run after `uv lock`:
docker build -t {name} .
docker run --rm {docker_run} {name}
```

The Compose port is published on `127.0.0.1` only. Configure authentication
before deliberately exposing an HTTP endpoint beyond the local machine.

Create and commit `uv.lock` before the Docker build. Initial dependency resolution
and installation require access to your dependency infrastructure. For an offline
deployment, build the image ahead of time and transfer it.

The included examples and smoke test are functional. Generated component skeletons
are intentionally incomplete until their business logic and assertions are implemented.

Documentation: https://gofastmcp.com/servers/server.md
'''
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": BUILDER_VERSION,
        "name": name,
        "template": template,
        "transport": transport,
        "fastmcp_version": FASTMCP_VERSION,
        "files": [{"path": path, "content": content} for path, content in files.items()],
    }
