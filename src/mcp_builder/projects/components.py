"""Deterministic FastMCP component skeletons with closed, safe input types."""

import keyword
import re
from urllib.parse import urlsplit

from .schemas import GenerationResult, PromptSpec, ResourceSpec, ToolSpec

REFERENCES = {
    "tool": "https://gofastmcp.com/servers/tools",
    "resource": "https://gofastmcp.com/servers/resources",
    "prompt": "https://gofastmcp.com/servers/prompts",
    "testing": "https://gofastmcp.com/servers/testing",
}


def _identifier(value: str, label: str = "Nom") -> str:
    """Validate a lowercase Python identifier used in a generated path."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) or keyword.iskeyword(value):
        raise ValueError(f"{label} attendu : identifiant Python minuscule, 1 à 64 caractères")
    return value


def _parameters(parameters) -> str:
    """Render validated parameters and reject duplicates or unsafe ordering."""
    seen: set[str] = set()
    rendered: list[str] = []
    optional_seen = False
    for parameter in parameters:
        name = _identifier(parameter.name, "Paramètre")
        if name in seen:
            raise ValueError(f"Paramètre dupliqué : {name}")
        seen.add(name)
        if not parameter.required:
            optional_seen = True
            annotation = f"Annotated[{parameter.type}, Field(description={parameter.description!r})]"
            rendered.append(f"{name}: {annotation} | None = None")
        elif optional_seen:
            raise ValueError("Les paramètres requis doivent précéder les paramètres optionnels")
        else:
            annotation = f"Annotated[{parameter.type}, Field(description={parameter.description!r})]"
            rendered.append(f"{name}: {annotation}")
    return ", ".join(rendered)


def _arguments(parameters) -> str:
    """Return deterministic JSON-compatible example arguments for a generated test."""
    examples = {
        "str": "example", "int": 1, "float": 1.0, "bool": True, "dict": {},
        "list[str]": [], "list[int]": [], "list[float]": [], "list[bool]": [],
        "dict[str, str]": {}, "dict[str, int]": {}, "dict[str, float]": {},
        "dict[str, bool]": {},
    }
    return repr({parameter.name: examples[parameter.type] for parameter in parameters
                 if parameter.required})


def _test(component: str, name: str, invocation: str) -> str:
    """Return an in-memory test that preserves the expected TODO failure."""
    return f'''"""Exercise the generated {component} through the in-memory FastMCP client."""

import pytest
from fastmcp import Client

from app.server import mcp


@pytest.mark.asyncio
async def test_{name}_todo_is_explicit():
    """Keep the component failing clearly until its business logic is implemented."""
    async with Client(mcp) as client:
        with pytest.raises(Exception, match="TODO"):
            {invocation}
'''


def _result(path: str, code: str, test: str, kind: str) -> GenerationResult:
    """Build the shared generator response envelope."""
    return GenerationResult(
        files=[{"path": path, "content": code},
               {"path": f"tests/test_{path.rsplit('/', 1)[-1]}", "content": test}],
        warnings=["Le squelette contient un TODO qui échoue jusqu'à son implémentation."],
        assumptions=["app.instance expose une instance FastMCP nommée mcp.",
                     "Le package du composant est importé explicitement par app.server."],
        references=[REFERENCES[kind], REFERENCES["testing"]],
    )


def generate_tool(spec: ToolSpec) -> GenerationResult:
    """Generate one dedicated tool module and its targeted test."""
    name = _identifier(spec.name)
    parameters = _parameters(spec.parameters)
    prefix = "async " if spec.is_async else ""
    code = f'''"""Register the {name} MCP tool."""

from typing import Annotated

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.instance import mcp


@mcp.tool(description={spec.description!r})
{prefix}def {name}({parameters}) -> {spec.return_type}:
    """Execute the generated tool contract."""
    raise ToolError("TODO: implement {name} business logic")
'''
    invocation = f'await client.call_tool("{name}", {_arguments(spec.parameters)})'
    return _result(f"app/tools/{name}.py", code, _test("tool", name, invocation), "tool")


def generate_resource(spec: ResourceSpec) -> GenerationResult:
    """Generate one dedicated resource module and its targeted test."""
    name = _identifier(spec.name)
    parsed = urlsplit(spec.uri)
    template_without_fields = re.sub(r"{[a-z][a-z0-9_]*}", "value", spec.uri)
    if (not parsed.scheme or any(char.isspace() for char in spec.uri)
            or ".." in (*parsed.path.split("/"), parsed.netloc)
            or "{" in template_without_fields or "}" in template_without_fields):
        raise ValueError("URI de resource absolue et sûre attendue")
    parameters = _parameters(spec.parameters)
    fields = set(re.findall(r"{([a-z][a-z0-9_]*)}", spec.uri))
    if fields != {parameter.name for parameter in spec.parameters}:
        raise ValueError("Les paramètres doivent correspondre exactement au template d'URI")
    prefix = "async " if spec.is_async else ""
    code = f'''"""Register the {name} MCP resource."""

from typing import Annotated

from pydantic import Field

from app.instance import mcp


@mcp.resource({spec.uri!r})
{prefix}def {name}({parameters}) -> {spec.return_type}:
    """Return the {name} resource."""
    raise RuntimeError("TODO: implement {name} resource logic")
'''
    concrete_uri = re.sub(r"{[^}]+}", "example", spec.uri)
    invocation = f'await client.read_resource("{concrete_uri}")'
    return _result(
        f"app/resources/{name}.py", code, _test("resource", name, invocation), "resource"
    )


def generate_prompt(spec: PromptSpec) -> GenerationResult:
    """Generate one dedicated prompt module and its targeted test."""
    name = _identifier(spec.name)
    parameters = _parameters(spec.arguments)
    prefix = "async " if spec.is_async else ""
    code = f'''"""Register the {name} MCP prompt."""

from typing import Annotated

from pydantic import Field

from app.instance import mcp


@mcp.prompt(description={spec.description!r})
{prefix}def {name}({parameters}) -> str:
    """Build the generated prompt contract."""
    raise RuntimeError("TODO: implement {name} prompt logic")
'''
    invocation = f'await client.get_prompt("{name}", {_arguments(spec.arguments)})'
    return _result(f"app/prompts/{name}.py", code, _test("prompt", name, invocation), "prompt")


def generate_component_test(kind: str, specification: dict) -> GenerationResult:
    """Regenerate the targeted test for a validated component specification."""
    generators = {
        "tool": (ToolSpec, generate_tool),
        "resource": (ResourceSpec, generate_resource),
        "prompt": (PromptSpec, generate_prompt),
    }
    if kind not in generators:
        raise ValueError("Type de composant attendu : tool, resource ou prompt")
    model, generator = generators[kind]
    result = generator(model.model_validate(specification))
    return result.model_copy(update={"files": [result.files[1]]})
