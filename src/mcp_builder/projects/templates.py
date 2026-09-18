"""Return deterministic project files; never write or execute them."""
import keyword
import re

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

from .examples import EXAMPLES
from .guide import GUIDE


def list_templates() -> list[dict]:
    """Return supported templates, parameters and the tested FastMCP version."""
    return [{"name": name, "description": description,
             "parameters": {"name": "Python identifier", "transport": ["http", "stdio"]},
             "fastmcp_version": FASTMCP_VERSION}
            for name, description in (
                ("minimal", "One module with a functional add tool"),
                ("structured", "Separate modules for tools, resources, and prompts"))]

def generate_project(name: str, template: str = "minimal", transport: str = "http") -> dict:
    """Return deterministic project files without writing to disk or executing code.

    name must be a lowercase Python identifier, template minimal/structured,
    and transport http/stdio. Invalid choices raise ValueError. The returned
    files include packaging, Docker, documentation and executable example tests;
    the client remains responsible for saving and adapting them.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or keyword.iskeyword(name):
        raise ValueError("Name must be a lowercase Python identifier, 1 to 64 characters")
    if template not in {"minimal", "structured"} or transport not in {"http", "stdio"}:
        raise ValueError("Unknown template or transport")
    files = {
        "app/__init__.py": '"""Example FastMCP application package."""\n',
        "pyproject.toml": f'''[build-system]
requires = ["hatchling==1.32.0"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastmcp=={FASTMCP_VERSION}"]

[dependency-groups]
dev = ["pytest==9.1.1", "pytest-asyncio==1.4.0"]

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
''',
        "Dockerfile": '''FROM python:3.14.6-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /uvx /usr/local/bin/
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
RUN uv sync --locked --no-dev --no-editable
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.server"]
''',
        ".dockerignore": ".venv\n__pycache__\n.git\n",
        ".gitignore": ".venv/\n__pycache__/\n.pytest_cache/\n",
        "MCP_BUILDER_GUIDE.md": GUIDE,
        "tests/test_server.py": EXAMPLES["testing"][1],
    }
    preamble = ('"""Create the shared MCP instance used by the application components."""\n\n'
                f'from fastmcp import FastMCP\n\nmcp = FastMCP("{name}")\n\n')
    if template == "minimal":
        server = preamble + EXAMPLES["tool"][1]
    else:
        files["app/instance.py"] = preamble
        server = ('"""Register components on import and start the selected transport when run."""\n\n'
                  "from app.instance import mcp\n"
                  "from app import tools, resources, prompts  # noqa: F401\n")
        components = (("tools", "add", "tool"), ("resources", "version", "resource"),
                      ("prompts", "explain", "prompt"))
        for package, module, topic in components:
            files[f"app/{package}/__init__.py"] = (
                f'"""Explicitly register the {topic} modules."""\n\n'
                f"from . import {module} as {module}\n"
            )
            files[f"app/{package}/{module}.py"] = (
                f'"""Register the example {topic} on the shared MCP instance."""\n\n'
                "from app.instance import mcp\n\n" + EXAMPLES[topic][1])
        files["tests/test_server.py"] += '''
@pytest.mark.asyncio
async def test_resources_and_prompts():
    """Check discovery and invocation of the version resource and explanation prompt."""
    async with Client(mcp) as client:
        assert await client.list_resources()
        assert await client.list_prompts()
        assert await client.read_resource("config://version")
        assert await client.get_prompt("explain", {"topic": "MCP"})
'''
    run = ('mcp.run(transport="http", host="0.0.0.0", port=8000)'
           if transport == "http" else 'mcp.run(transport="stdio")')
    files["app/server.py"] = server + f'\n\nif __name__ == "__main__":\n    {run}\n'
    files["README.md"] = f'''# {name}

FastMCP {FASTMCP_VERSION} server using the {transport} transport.

Read [MCP_BUILDER_GUIDE.md](MCP_BUILDER_GUIDE.md) before adding a component.

```bash
uv lock
uv sync --locked
uv run --locked pytest
uv run --locked python -m app.server
```

{"Endpoint: http://localhost:8000/mcp" if transport == "http" else "Configure the client to run python -m app.server from the project directory."}

```bash
docker build -t {name} .
docker run --rm {"-p 8000:8000" if transport == "http" else "-i"} {name}
```

Create and commit `uv.lock` before the Docker build. Initial dependency resolution
and installation require access to your dependency infrastructure.
For an offline deployment, build the image ahead of time and transfer it.
The examples are functional; adapt the tools to your business requirements.
Documentation: https://gofastmcp.com/servers/server.md
'''
    return {"schema_version": SCHEMA_VERSION, "generator_version": BUILDER_VERSION,
            "name": name, "template": template, "transport": transport,
            "fastmcp_version": FASTMCP_VERSION,
            "files": [{"path": path, "content": content} for path, content in files.items()]}
