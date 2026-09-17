"""Return deterministic project files; never write or execute them."""
import keyword
import re

from mcp_builder import FASTMCP_VERSION

from .examples import EXAMPLES


def list_templates() -> list[dict]:
    """Return supported templates, parameters and the tested FastMCP version."""
    return [{"name": name, "description": description,
             "parameters": {"name": "Python identifier", "transport": ["http", "stdio"]},
             "fastmcp_version": FASTMCP_VERSION}
            for name, description in (
                ("minimal", "Un module avec un outil add fonctionnel"),
                ("structured", "Modules séparés pour tools, resources et prompts"))]

def generate_project(name: str, template: str = "minimal", transport: str = "http") -> dict:
    """Return deterministic project files without writing to disk or executing code.

    name must be a lowercase Python identifier, template minimal/structured,
    and transport http/stdio. Invalid choices raise ValueError. The returned
    files include packaging, Docker, documentation and executable example tests;
    the client remains responsible for saving and adapting them.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or keyword.iskeyword(name):
        raise ValueError("Nom attendu : identifiant Python minuscule, 1 à 64 caractères")
    if template not in {"minimal", "structured"} or transport not in {"http", "stdio"}:
        raise ValueError("Modèle ou transport inconnu")
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
        for module, topic in [("tools", "tool"), ("resources", "resource"), ("prompts", "prompt")]:
            files[f"app/{module}.py"] = (
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

Serveur FastMCP {FASTMCP_VERSION} — transport {transport}.

```bash
uv lock
uv sync --locked
uv run --locked pytest
uv run --locked python -m app.server
```

{"Endpoint : http://localhost:8000/mcp" if transport == "http" else "Configurer le client avec python -m app.server dans le dossier du projet."}

```bash
docker build -t {name} .
docker run --rm {"-p 8000:8000" if transport == "http" else "-i"} {name}
```

Créer puis versionner `uv.lock` avant le build Docker. La résolution initiale
et l'installation nécessitent l'accès aux dépendances de votre infrastructure.
Pour un déploiement hors ligne, construire l'image en amont puis la transférer.
Les exemples sont fonctionnels ; adaptez les outils au besoin métier.
Documentation : https://gofastmcp.com/servers/server.md
'''
    return {"name": name, "template": template, "transport": transport,
            "fastmcp_version": FASTMCP_VERSION,
            "files": [{"path": path, "content": content} for path, content in files.items()]}
