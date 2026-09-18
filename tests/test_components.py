"""Tests for deterministic component and structured-project generation."""

import ast
import hashlib

import pytest
from pydantic import ValidationError

from mcp_builder.projects import (
    generate_component_test,
    generate_project,
    generate_prompt,
    generate_resource,
    generate_tool,
    inspect_project,
    propose_project_patch,
    review_project_security,
    validate_project,
)
from mcp_builder.projects.schemas import PromptSpec, ResourceSpec, ToolSpec


def _files(result):
    """Index generated Pydantic files by path."""
    return {item.path: item.content for item in result.files}


def test_each_component_generator_returns_valid_python_and_common_envelope():
    """All generators create one component file plus one targeted test."""
    results = [
        generate_tool(ToolSpec(name="lookup", description="Look up a value.",
                               parameters=[], return_type="str", is_async=True)),
        generate_resource(ResourceSpec(name="record", uri="record://{record_id}",
                                       parameters=[{"name": "record_id", "type": "str",
                                                    "description": "Record identifier."}],
                                       return_type="dict")),
        generate_prompt(PromptSpec(name="explain", description="Explain a topic.",
                                   arguments=[], is_async=False)),
    ]
    for result in results:
        assert result.warnings and result.assumptions and len(result.references) == 2
        assert len(result.files) == 2
        for content in _files(result).values():
            ast.parse(content)


@pytest.mark.parametrize("name", ["../escape", "Upper", "class", "a-b"])
def test_generators_reject_unsafe_names(name):
    """Names can never become traversing or arbitrary Python paths."""
    spec = ToolSpec(name=name, description="Invalid name.", return_type="str")
    with pytest.raises(ValueError):
        generate_tool(spec)


def test_closed_types_and_resource_templates_are_validated():
    """Arbitrary annotations and mismatched URI fields are rejected."""
    with pytest.raises(ValidationError):
        ToolSpec(name="bad", description="Bad type.", return_type="os.system('x')")
    with pytest.raises(ValidationError):
        ToolSpec(name="bad", description="Extra input.", return_type="str", python="import os")
    spec = ResourceSpec(name="record", uri="record://{missing}", parameters=[],
                        return_type="str")
    with pytest.raises(ValueError, match="exactly match"):
        generate_resource(spec)


def test_component_test_returns_only_the_test_file():
    """Targeted test regeneration does not repeat the component module."""
    result = generate_component_test("prompt", {
        "name": "help", "description": "Help the user.", "arguments": [],
    })
    assert [item.path for item in result.files] == ["tests/test_help.py"]


def test_structured_project_has_explicit_packages_guide_and_valid_layout():
    """The structured template follows one-file-per-tool and explicit imports."""
    project = generate_project("example", "structured", "http")
    files = {item["path"]: item["content"] for item in project["files"]}
    required = {
        "app/tools/__init__.py", "app/tools/add.py", "app/resources/__init__.py",
        "app/resources/version.py", "app/prompts/__init__.py", "app/prompts/explain.py",
        "MCP_BUILDER_GUIDE.md",
    }
    assert required <= files.keys()
    assert "MCP_BUILDER_GUIDE.md" in files["README.md"]
    assert "Mandatory MCP Builder workflow" in files["MCP_BUILDER_GUIDE.md"]
    assert "call `validate_project` again" in files["MCP_BUILDER_GUIDE.md"]
    for path, content in files.items():
        if path.endswith(".py"):
            ast.parse(content)
    validation = validate_project(project["files"])
    assert validation["valid"] is True
    assert not [item for item in validation["diagnostics"] if item["severity"] == "error"]


def test_validator_enforces_one_tool_per_matching_exported_file():
    """Layout, multiplicity and explicit registration are static errors."""
    report = validate_project([{"path": "app/tools/wrong.py", "content": '''
from app.instance import mcp
@mcp.tool
def first() -> str:
    return "one"
@mcp.tool
def second() -> str:
    return "two"
'''}])
    codes = {item["code"] for item in report["diagnostics"]}
    assert {"multiple_tools_in_file", "tool_file_layout", "component_not_exported"} <= codes


def test_validator_warns_for_todo_skeleton():
    """An explicit TODO remains valid but visible to callers."""
    report = validate_project([{"path": "app/example.py", "content": "# TODO\nvalue = 1\n"}])
    assert report["valid"] is True
    assert report["diagnostics"][0]["code"] == "todo_skeleton"
    assert report["diagnostics"][0]["suggestion"]
    assert report["diagnostics"][0]["documentation"].startswith("https://")


def test_inspection_maps_components_models_dependencies_and_tests():
    """Inspection returns an actionable static inventory without executing files."""
    project = generate_project("example", "structured", "http")
    project["files"].append({
        "path": "app/models.py",
        "content": "from pydantic import BaseModel\nclass Input(BaseModel):\n    value: str\n",
    })
    result = inspect_project(project["files"])
    assert result.executed is False
    assert result.schema_version == "1"
    assert result.declared_fastmcp_version == "4.0.3"
    assert result.architecture["component_counts"] == {
        "tool": 1, "resource": 1, "prompt": 1,
    }
    assert {item.function for item in result.components} == {"add", "version", "explain"}
    assert all(item.exported for item in result.components)
    assert result.pydantic_models[0]["name"] == "Input"


def test_patch_proposal_guards_replacements_and_registers_component():
    """Patch proposals include optimistic hashes and an explicit package import."""
    original = '"""Old tool."""\n'
    init = '"""Tools."""\n'
    result = propose_project_patch("tool", {
        "name": "lookup", "description": "Look up a value.", "parameters": [],
        "return_type": "str", "is_async": False,
    }, [
        {"path": "app/tools/lookup.py", "content": original},
        {"path": "app/tools/__init__.py", "content": init},
    ])
    changes = {item.path: item for item in result.changes}
    assert changes["app/tools/lookup.py"].operation == "replace"
    assert changes["app/tools/lookup.py"].original_sha256 == hashlib.sha256(
        original.encode()
    ).hexdigest()
    assert changes["tests/test_lookup.py"].operation == "create"
    assert "from . import lookup as lookup" in changes["app/tools/__init__.py"].content
    assert result.executed is False


def test_security_diagnostics_are_specific_and_repairable():
    """High-confidence unsafe patterns receive stable diagnostic codes and guidance."""
    report = validate_project([
        {"path": "app/tools/fetch.py", "content": '''
from app.instance import mcp
@mcp.tool
async def fetch(api_key: str) -> str:
    requests.get("https://example.test")
    return api_key
'''},
        {"path": "app/tools/__init__.py", "content": "from . import fetch as fetch\n"},
    ])
    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert {"secret_argument", "blocking_call_in_async", "network_without_timeout"} \
        <= diagnostics.keys()
    assert all(item["suggestion"] and item["documentation"]
               for item in diagnostics.values())
    security = review_project_security([
        {"path": "app/tools/fetch.py", "content": '''
from app.instance import mcp
@mcp.tool
def fetch(token: str) -> str:
    return token
'''},
        {"path": "app/tools/__init__.py", "content": "from . import fetch as fetch\n"},
    ])
    assert security["passed"] is False
    assert security["diagnostics"][0]["code"] == "secret_argument"
    assert security["executed"] is False
