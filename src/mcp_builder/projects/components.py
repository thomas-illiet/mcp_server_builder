"""Deterministic FastMCP component skeletons with closed, safe input types."""

import keyword
import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from .schemas import (
    EnumDefinition,
    GenerationResult,
    ObjectDefinition,
    PromptSpec,
    ResourceSpec,
    ToolSpec,
    TypeDefinition,
)

REFERENCES = {
    "tool": "https://gofastmcp.com/servers/tools",
    "resource": "https://gofastmcp.com/servers/resources",
    "prompt": "https://gofastmcp.com/servers/prompts",
    "testing": "https://gofastmcp.com/servers/testing",
}


def _identifier(value: str, label: str = "Name") -> str:
    """Validate a lowercase Python identifier used in a generated path."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) or keyword.iskeyword(value):
        raise ValueError(f"{label} must be a lowercase Python identifier, 1 to 64 characters")
    return value


def _named_reference(annotation: str) -> str | None:
    """Extract a named model reference from a closed component annotation."""
    match = re.fullmatch(r"(?:list\[)?([A-Z][A-Za-z0-9]{0,63})(?:\])?", annotation)
    return match.group(1) if match else None


def _prepare_definitions(
    definitions: Iterable[TypeDefinition], used_types: Iterable[str]
) -> tuple[list[TypeDefinition], dict[str, TypeDefinition]]:
    """Validate references and order model definitions without executing source."""
    supplied = list(definitions)
    names = [definition.name for definition in supplied]
    if len(names) != len(set(names)):
        raise ValueError("Type definition names must be unique")
    by_name = {definition.name: definition for definition in supplied}
    for annotation in used_types:
        reference = _named_reference(annotation)
        if reference is not None and reference not in by_name:
            raise ValueError(f"Unknown named type: {reference}")

    ordered: list[TypeDefinition] = [
        definition for definition in supplied if isinstance(definition, EnumDefinition)
    ]
    pending = [definition for definition in supplied if isinstance(definition, ObjectDefinition)]
    resolved = {definition.name for definition in ordered}
    while pending:
        progress = False
        for definition in list(pending):
            references = {
                reference
                for field in definition.fields
                if (reference := _named_reference(field.type)) is not None
            }
            unknown = references - by_name.keys()
            if unknown:
                raise ValueError(f"Unknown named type: {sorted(unknown)[0]}")
            if references <= resolved:
                ordered.append(definition)
                resolved.add(definition.name)
                pending.remove(definition)
                progress = True
        if not progress:
            raise ValueError("Object type definitions must not contain reference cycles")
    return ordered, by_name


def _annotation(parameter) -> str:
    """Render one validated parameter or model-field annotation."""
    return f"Annotated[{parameter.type}, Field(description={parameter.description!r})]"


def _parameters(parameters) -> str:
    """Render validated parameters and reject duplicates or unsafe ordering."""
    seen: set[str] = set()
    rendered: list[str] = []
    optional_seen = False
    for parameter in parameters:
        name = _identifier(parameter.name, "Parameter")
        if name in seen:
            raise ValueError(f"Duplicate parameter: {name}")
        seen.add(name)
        annotation = _annotation(parameter)
        if not parameter.required:
            optional_seen = True
            rendered.append(f"{name}: {annotation} | None = None")
        elif optional_seen:
            raise ValueError("Required parameters must precede optional parameters")
        else:
            rendered.append(f"{name}: {annotation}")
    return ", ".join(rendered)


def _enum_member(value: str, index: int, used: set[str]) -> str:
    """Return a stable valid Python member name for an arbitrary enum value."""
    base = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_").upper() or "VALUE"
    if base[0].isdigit() or keyword.iskeyword(base.lower()):
        base = f"VALUE_{base}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _render_definitions(definitions: list[TypeDefinition]) -> str:
    """Render bounded enums and Pydantic objects before a component function."""
    blocks: list[str] = []
    for definition in definitions:
        if isinstance(definition, EnumDefinition):
            used: set[str] = set()
            members = "\n".join(
                f"    {_enum_member(value, index, used)} = {value!r}"
                for index, value in enumerate(definition.values)
            )
            blocks.append(
                f'class {definition.name}(str, Enum):\n'
                f'    """Allowed values for {definition.name}."""\n\n{members}'
            )
            continue
        fields = "\n".join(
            (
                f"    {_identifier(field.name, 'Field')}: {_annotation(field)}"
                if field.required
                else (
                    f"    {_identifier(field.name, 'Field')}: "
                    f"{_annotation(field)} | None = None"
                )
            )
            for field in definition.fields
        )
        blocks.append(
            f'class {definition.name}(BaseModel):\n'
            f'    """Structured {definition.name} contract."""\n\n{fields}'
        )
    return "\n\n\n".join(blocks)


def _imports(
    definitions: list[TypeDefinition], *, has_parameters: bool, tool_error: bool = False
) -> str:
    """Return a Ruff-sorted import block containing only names the module uses."""
    has_objects = any(isinstance(item, ObjectDefinition) for item in definitions)
    standard_library: list[str] = []
    third_party: list[str] = []
    if any(isinstance(item, EnumDefinition) for item in definitions):
        standard_library.append("from enum import Enum")
    if has_parameters or has_objects:
        standard_library.append("from typing import Annotated")
    if tool_error:
        third_party.append("from fastmcp.exceptions import ToolError")
    if has_parameters or has_objects:
        pydantic = "BaseModel, Field" if has_objects else "Field"
        third_party.append(f"from pydantic import {pydantic}")
    groups = [standard_library, third_party, ["from app.instance import mcp"]]
    return "\n\n".join("\n".join(group) for group in groups if group)


def _example(annotation: str, definitions: dict[str, TypeDefinition]):
    """Return one deterministic JSON-compatible example for a closed type."""
    examples = {
        "str": "example",
        "int": 1,
        "float": 1.0,
        "bool": True,
        "dict": {},
        "list[str]": [],
        "list[int]": [],
        "list[float]": [],
        "list[bool]": [],
        "dict[str, str]": {},
        "dict[str, int]": {},
        "dict[str, float]": {},
        "dict[str, bool]": {},
    }
    if annotation in examples:
        return examples[annotation]
    if annotation.startswith("list["):
        return []
    definition = definitions[annotation]
    if isinstance(definition, EnumDefinition):
        return definition.values[0]
    return {
        field.name: _example(field.type, definitions)
        for field in definition.fields
        if field.required
    }


def _arguments(parameters, definitions: dict[str, TypeDefinition]) -> str:
    """Return deterministic JSON-compatible example arguments for a generated test."""
    return repr(
        {
            parameter.name: _example(parameter.type, definitions)
            for parameter in parameters
            if parameter.required
        }
    )


def _test(component: str, name: str, invocation: str) -> str:
    """Return an explicitly failing test until real assertions are supplied."""
    return f'''"""Exercise the generated {component} through the in-memory FastMCP client."""

import pytest
from fastmcp import Client

from app.server import mcp


@pytest.mark.asyncio
async def test_{name}_contract_is_implemented():
    """Replace the placeholder with assertions for the implemented business contract."""
    async with Client(mcp) as client:
        result = {invocation}
        pytest.fail(
            f"TODO: assert the {name} business result after implementation; got {{result!r}}"
        )
'''


def _result(path: str, code: str, test: str, kind: str) -> GenerationResult:
    """Build the shared generator response envelope."""
    return GenerationResult(
        files=[
            {"path": path, "content": code},
            {"path": f"tests/test_{path.rsplit('/', 1)[-1]}", "content": test},
        ],
        warnings=[
            "The component and its focused test intentionally fail until business logic "
            "and meaningful assertions are implemented."
        ],
        assumptions=[
            "app.instance exposes a FastMCP instance named mcp.",
            "The component package is imported explicitly by app.server.",
        ],
        references=[REFERENCES[kind], REFERENCES["testing"]],
    )


def _contract_parts(
    spec, parameters, *, tool_error: bool = False
) -> tuple[str, str, dict[str, TypeDefinition]]:
    """Validate referenced definitions and render their declarations."""
    used_types = [parameter.type for parameter in parameters]
    if hasattr(spec, "return_type"):
        used_types.append(spec.return_type)
    used_types.extend(
        field.type
        for definition in spec.definitions
        if isinstance(definition, ObjectDefinition)
        for field in definition.fields
    )
    definitions, by_name = _prepare_definitions(spec.definitions, used_types)
    declarations = _render_definitions(definitions)
    imports = _imports(
        definitions,
        has_parameters=bool(parameters),
        tool_error=tool_error,
    )
    return imports, declarations, by_name


def generate_tool(spec: ToolSpec) -> GenerationResult:
    """Generate one dedicated tool module and its targeted failing test."""
    name = _identifier(spec.name)
    parameters = _parameters(spec.parameters)
    imports, declarations, definitions = _contract_parts(
        spec, spec.parameters, tool_error=True
    )
    prelude = f"{imports}\n\n\n{declarations}" if declarations else imports
    prefix = "async " if spec.is_async else ""
    code = f'''"""Register the {name} MCP tool."""

{prelude}


@mcp.tool(description={spec.description!r})
{prefix}def {name}({parameters}) -> {spec.return_type}:
    """Execute the generated tool contract."""
    raise ToolError("TODO: implement {name} business logic")
'''
    invocation = f'await client.call_tool("{name}", {_arguments(spec.parameters, definitions)})'
    return _result(f"app/tools/{name}.py", code, _test("tool", name, invocation), "tool")


def generate_resource(spec: ResourceSpec) -> GenerationResult:
    """Generate one dedicated resource module and its targeted failing test."""
    name = _identifier(spec.name)
    parsed = urlsplit(spec.uri)
    template_without_fields = re.sub(r"{[a-z][a-z0-9_]*}", "value", spec.uri)
    if (
        not parsed.scheme
        or any(char.isspace() for char in spec.uri)
        or ".." in (*parsed.path.split("/"), parsed.netloc)
        or "{" in template_without_fields
        or "}" in template_without_fields
    ):
        raise ValueError("Expected an absolute, safe resource URI")
    parameters = _parameters(spec.parameters)
    fields = set(re.findall(r"{([a-z][a-z0-9_]*)}", spec.uri))
    if fields != {parameter.name for parameter in spec.parameters}:
        raise ValueError("Parameters must exactly match the URI template")
    imports, declarations, definitions = _contract_parts(spec, spec.parameters)
    prelude = f"{imports}\n\n\n{declarations}" if declarations else imports
    prefix = "async " if spec.is_async else ""
    code = f'''"""Register the {name} MCP resource."""

{prelude}


@mcp.resource({spec.uri!r})
{prefix}def {name}({parameters}) -> {spec.return_type}:
    """Return the {name} resource."""
    raise RuntimeError("TODO: implement {name} resource logic")
'''
    concrete_uri = re.sub(r"{[^}]+}", "example", spec.uri)
    invocation = f'await client.read_resource("{concrete_uri}")'
    return _result(
        f"app/resources/{name}.py",
        code,
        _test("resource", name, invocation),
        "resource",
    )


def generate_prompt(spec: PromptSpec) -> GenerationResult:
    """Generate one dedicated prompt module and its targeted failing test."""
    name = _identifier(spec.name)
    parameters = _parameters(spec.arguments)
    imports, declarations, definitions = _contract_parts(spec, spec.arguments)
    prelude = f"{imports}\n\n\n{declarations}" if declarations else imports
    prefix = "async " if spec.is_async else ""
    code = f'''"""Register the {name} MCP prompt."""

{prelude}


@mcp.prompt(description={spec.description!r})
{prefix}def {name}({parameters}) -> str:
    """Build the generated prompt contract."""
    raise RuntimeError("TODO: implement {name} prompt logic")
'''
    invocation = f'await client.get_prompt("{name}", {_arguments(spec.arguments, definitions)})'
    return _result(f"app/prompts/{name}.py", code, _test("prompt", name, invocation), "prompt")


def generate_component_test(kind: str, specification: dict) -> GenerationResult:
    """Regenerate the targeted test for a validated component specification."""
    generators = {
        "tool": (ToolSpec, generate_tool),
        "resource": (ResourceSpec, generate_resource),
        "prompt": (PromptSpec, generate_prompt),
    }
    if kind not in generators:
        raise ValueError("Expected component type: tool, resource, or prompt")
    model, generator = generators[kind]
    result = generator(model.model_validate(specification))
    return result.model_copy(update={"files": [result.files[1]]})
