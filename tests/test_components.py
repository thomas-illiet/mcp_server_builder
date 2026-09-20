"""Tests for deterministic component and structured-project generation."""

import ast
import subprocess
import sys

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
        test = result.files[1].content
        assert "pytest.raises" not in test
        assert "pytest.fail" in test


@pytest.mark.parametrize("kind", ["tool", "resource", "prompt"])
def test_zero_argument_component_source_is_ruff_clean(tmp_path, kind):
    """Optional imports and spacing stay valid for every zero-argument component."""
    project = generate_project("example", "minimal", "http")
    for item in project["files"]:
        target = tmp_path / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8")
    if kind == "tool":
        generated = generate_tool(ToolSpec(
            name="ping", description="Return a pong.", return_type="str"
        ))
    elif kind == "resource":
        generated = generate_resource(ResourceSpec(
            name="status", uri="status://current", return_type="dict"
        ))
    else:
        generated = generate_prompt(PromptSpec(
            name="help", description="Return usage help."
        ))
    for item in generated.files:
        target = tmp_path / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("name", ["../escape", "Upper", "class", "a-b"])
def test_generators_reject_unsafe_names(name):
    """Names can never become traversing or arbitrary Python paths."""
    with pytest.raises(ValidationError):
        ToolSpec(name=name, description="Invalid name.", return_type="str")


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
        "app/instance.py", ".env.example", "AGENTS.md", "compose.yaml",
        "MCP_BUILDER_GUIDE.md", "tests/test_smoke.py",
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
    assert validation["ready"] is True
    assert not [item for item in validation["diagnostics"] if item["severity"] == "error"]


def test_minimal_project_uses_shared_instance_and_extensible_packages():
    """The minimal template can receive every component type without re-architecture."""
    project = generate_project("example", "minimal", "stdio")
    files = {item["path"]: item["content"] for item in project["files"]}
    assert {
        "app/instance.py",
        "app/tools/__init__.py",
        "app/resources/__init__.py",
        "app/prompts/__init__.py",
    } <= files.keys()
    assert "from app.instance import mcp" in files["app/server.py"]
    assert "from app import prompts, resources, tools" in files["app/server.py"]
    assert "ports:" not in files["compose.yaml"]


def test_structured_is_the_default_and_compose_is_local_only():
    """The recommended template and loopback-only HTTP publication are the safe defaults."""
    project = generate_project("example")
    files = {item["path"]: item["content"] for item in project["files"]}
    assert project["template"] == "structured"
    assert '"127.0.0.1:8000:8000"' in files["compose.yaml"]
    assert "cap_drop:" in files["compose.yaml"]
    assert "read_only: true" in files["compose.yaml"]


@pytest.mark.parametrize("template", ["minimal", "structured"])
def test_each_template_imports_discovers_and_invokes(tmp_path, template):
    """Each generated architecture passes its real in-process MCP smoke test."""
    project = generate_project("example", template, "http")
    for item in project["files"]:
        if not item["path"].endswith(".py"):
            continue
        target = tmp_path / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_smoke.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_validator_enforces_one_tool_per_matching_exported_file():
    """House conventions warn by default and become errors only under strict policy."""
    files = [{"path": "app/tools/wrong.py", "content": '''
from app.instance import mcp
@mcp.tool
def first() -> str:
    return "one"
@mcp.tool
def second() -> str:
    return "two"
'''}]
    recommended = validate_project(files)
    assert recommended["valid"] is True
    report = validate_project(files, profile="strict")
    codes = {item["code"] for item in report["diagnostics"]}
    assert {"multiple_tools_in_file", "tool_file_layout", "component_not_exported"} <= codes
    assert report["valid"] is False

    framework = validate_project(files, profile="framework")
    assert framework["valid"] is True
    assert not ({"multiple_tools_in_file", "tool_file_layout", "component_not_exported"}
                & {item["code"] for item in framework["diagnostics"]})


def test_validator_warns_for_todo_skeleton():
    """A TODO remains valid source while blocking readiness."""
    report = validate_project([{"path": "app/example.py", "content": "# TODO\nvalue = 1\n"}])
    assert report["valid"] is True
    assert report["ready"] is False
    assert report["diagnostics"][0]["code"] == "todo_skeleton"
    assert report["readiness_issues"][0]["code"] == "todo_skeleton"
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
    assert all(item.targeted_test for item in result.components)
    assert result.pydantic_models[0]["name"] == "Input"


def test_patch_proposal_returns_conflict_instead_of_replacing_existing_code():
    """Existing component code is never replaced by a generated TODO skeleton."""
    original = '"""Old tool."""\n'
    init = '"""Tools."""\n'
    result = propose_project_patch("tool", {
        "name": "lookup", "description": "Look up a value.", "parameters": [],
        "return_type": "str", "is_async": False,
    }, [
        {"path": "app/tools/lookup.py", "content": original},
        {"path": "app/tools/__init__.py", "content": init},
    ])
    assert result.changes == []
    assert [item.path for item in result.conflicts] == ["app/tools/lookup.py"]
    assert result.conflicts[0].original_sha256
    assert result.executed is False


def test_patch_proposal_creates_new_files_and_registers_component():
    """A new component gets create-only changes and a guarded init update."""
    result = propose_project_patch("tool", {
        "name": "lookup", "description": "Look up a value.", "parameters": [],
        "return_type": "str", "is_async": False,
    }, [{"path": "app/tools/__init__.py", "content": '"""Tools."""\n'}])
    changes = {item.path: item for item in result.changes}
    assert changes["app/tools/lookup.py"].operation == "create"
    assert changes["tests/test_lookup.py"].operation == "create"
    assert changes["app/tools/__init__.py"].operation == "replace"
    assert "from . import lookup as lookup" in changes["app/tools/__init__.py"].content
    assert result.conflicts == []


def test_targeted_tests_are_detected_by_content_not_filename():
    """A semantic client call with an assertion counts regardless of the test filename."""
    files = [
        {"path": "app/tools/lookup.py", "content": '''
from app.instance import mcp
@mcp.tool
def lookup() -> str:
    """Look up a value."""
    return "value"
'''},
        {"path": "app/tools/__init__.py", "content": "from . import lookup as lookup\n"},
        {"path": "tests/behavior_contract.py", "content": '''
from fastmcp import Client
from app.server import mcp
async def test_lookup_behavior():
    async with Client(mcp) as client:
        result = await client.call_tool("lookup", {})
        assert result.data == "value"
'''},
    ]
    report = validate_project(files)
    assert "missing_targeted_test" not in {item["code"] for item in report["diagnostics"]}
    inspected = inspect_project(files)
    assert inspected.components[0].targeted_test is True


def test_filename_alone_does_not_count_as_a_targeted_test():
    """A same-named test file without component invocation is not verification evidence."""
    files = [
        {"path": "app/tools/lookup.py", "content": '''
from app.instance import mcp
@mcp.tool
def lookup() -> str:
    """Look up a value."""
    return "value"
'''},
        {"path": "app/tools/__init__.py", "content": "from . import lookup as lookup\n"},
        {"path": "tests/test_lookup.py", "content": "def test_placeholder():\n    assert True\n"},
    ]
    report = validate_project(files)
    assert "missing_targeted_test" in {item["code"] for item in report["readiness_issues"]}
    assert report["valid"] is True
    assert report["ready"] is False


def test_unrelated_assertion_and_unresolved_call_do_not_count_as_a_targeted_test():
    """A syntactically similar call must be imported and its result must be asserted."""
    files = [
        {"path": "app/tools/lookup.py", "content": '''
from app.instance import mcp
@mcp.tool
def lookup() -> str:
    """Look up a value."""
    return "value"
'''},
        {"path": "app/tools/__init__.py", "content": "from . import lookup as lookup\n"},
        {"path": "tests/behavior_contract.py", "content": '''
def test_lookup_behavior():
    lookup()
    assert True
'''},
    ]
    report = validate_project(files)
    assert "missing_targeted_test" in {item["code"] for item in report["readiness_issues"]}


def test_remote_homonym_and_broad_exception_do_not_prove_a_component():
    """Tests must bind to app.server and cannot accept every exception as success."""
    component = {"path": "app/tools/lookup.py", "content": '''
from app.instance import mcp
@mcp.tool
def lookup() -> str:
    """Look up a value."""
    raise NotImplementedError()
'''}
    registration = {
        "path": "app/tools/__init__.py",
        "content": "from . import lookup as lookup\n",
    }
    remote = {"path": "tests/behavior_contract.py", "content": '''
from fastmcp import Client


async def test_lookup_behavior():
    async with Client("http://elsewhere.invalid/mcp") as client:
        result = await client.call_tool("lookup", {})
        assert result.data == "value"
'''}
    report = validate_project([component, registration, remote])
    codes = {item["code"] for item in report["readiness_issues"]}
    assert {"incomplete_component", "missing_targeted_test"} <= codes

    broad = {"path": "tests/behavior_contract.py", "content": '''
import pytest
from fastmcp import Client

from app.server import mcp


async def test_lookup_behavior():
    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.call_tool("lookup", {})
'''}
    report = validate_project([component, registration, broad])
    assert "missing_targeted_test" in {
        item["code"] for item in report["readiness_issues"]
    }


def test_direct_import_and_result_assertion_count_as_a_targeted_test():
    """A direct component test is recognized through its explicit import and data flow."""
    files = [
        {"path": "app/tools/lookup.py", "content": '''
from app.instance import mcp
@mcp.tool
def lookup() -> str:
    """Look up a value."""
    return "value"
'''},
        {"path": "app/tools/__init__.py", "content": "from . import lookup as lookup\n"},
        {"path": "tests/behavior_contract.py", "content": '''
from app.tools.lookup import lookup


def test_lookup_behavior():
    value = lookup()
    assert value == "value"
'''},
    ]
    report = validate_project(files)
    assert "missing_targeted_test" not in {
        item["code"] for item in report["readiness_issues"]
    }


def test_component_generator_supports_enums_models_arrays_and_structured_output():
    """Closed definitions render valid typed Pydantic input and output contracts."""
    result = generate_tool(ToolSpec.model_validate({
        "name": "search", "description": "Search records.",
        "parameters": [{"name": "query", "type": "Query", "description": "Search input."}],
        "return_type": "list[Record]",
        "definitions": [
            {"kind": "enum", "name": "Scope", "values": ["title", "full-text"]},
            {"kind": "object", "name": "Query", "fields": [
                {"name": "text", "type": "str", "description": "Search text."},
                {"name": "scope", "type": "Scope", "description": "Search scope."},
            ]},
            {"kind": "object", "name": "Record", "fields": [
                {"name": "identifier", "type": "str", "description": "Record ID."},
                {"name": "tags", "type": "list[str]", "description": "Record tags.",
                 "required": False},
            ]},
        ],
    }))
    code = result.files[0].content
    ast.parse(code)
    assert "class Scope(str, Enum):" in code
    assert "class Query(BaseModel):" in code
    assert "-> list[Record]:" in code
    assert "'query': {'text': 'example', 'scope': 'title'}" in result.files[1].content


@pytest.mark.parametrize("reserved", ["None", "True", "False"])
def test_generated_type_names_reject_python_constants(reserved):
    """Type definitions can never produce syntactically invalid class declarations."""
    with pytest.raises(ValidationError):
        ToolSpec.model_validate({
            "name": "lookup",
            "description": "Look up a record.",
            "parameters": [],
            "return_type": reserved,
            "definitions": [{"kind": "object", "name": reserved, "fields": [{
                "name": "value", "type": "str", "description": "Stored value.",
            }]}],
        })


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


@pytest.mark.parametrize(
    "source",
    [
        '''
from subprocess import run


def helper(command: str) -> str:
    run(command)
    return "done"
''',
        '''
import subprocess as process


def helper(command: str) -> str:
    process.Popen(command)
    return "done"
''',
    ],
)
def test_security_resolves_subprocess_import_aliases(source):
    """Direct imports and module aliases cannot hide dynamic process execution."""
    security = review_project_security([
        {"path": "app/helpers.py", "content": source},
    ])
    assert security["passed"] is False
    assert "dangerous_process_call" in {
        item["code"] for item in security["diagnostics"]
    }


@pytest.mark.parametrize(
    "import_line,call",
    [
        ("from requests import get", "get(url)"),
        ("from requests import get as fetch", "fetch(url)"),
        ("import requests as web", "web.get(url)"),
    ],
)
def test_security_resolves_requests_get_aliases(import_line, call):
    """Every common requests.get import form retains timeout and async diagnostics."""
    report = validate_project([{
        "path": "app/helpers.py",
        "content": f'''{import_line}


async def helper(url: str) -> str:
    response = {call}
    return response.text
''',
    }], profile="framework")
    codes = {item["code"] for item in report["diagnostics"]}
    assert {"blocking_call_in_async", "network_without_timeout"} <= codes


@pytest.mark.parametrize(
    "source",
    [
        '''
from httpx import Client as SyncClient


async def helper(url: str) -> str:
    with SyncClient(timeout=5) as client:
        response = client.get(url)
    return response.text
''',
        '''
from requests import Session as SyncClient


async def helper(url: str) -> str:
    with SyncClient() as client:
        response = client.get(url, timeout=5)
    return response.text
''',
    ],
)
def test_security_tracks_sync_http_client_aliases_inside_async_functions(source):
    """A constructor timeout does not conceal synchronous HTTP I/O in async code."""
    report = validate_project([{
        "path": "app/helpers.py",
        "content": source,
    }], profile="framework")
    codes = {item["code"] for item in report["diagnostics"]}
    assert "blocking_call_in_async" in codes
    assert "network_without_timeout" not in codes


def test_security_does_not_treat_async_http_client_alias_as_blocking():
    """Alias resolution distinguishes HTTPX's asynchronous client from its sync client."""
    report = validate_project([{
        "path": "app/helpers.py",
        "content": '''
from httpx import AsyncClient as WebClient


async def helper(url: str) -> str:
    async with WebClient(timeout=5) as client:
        response = await client.get(url)
    return response.text
''',
    }], profile="framework")
    codes = {item["code"] for item in report["diagnostics"]}
    assert "blocking_call_in_async" not in codes
    assert "network_without_timeout" not in codes


def test_helpers_are_scanned_without_rejecting_safe_process_or_exception_pass():
    """Essential checks cross helper boundaries while allowing bounded Python patterns."""
    unsafe = review_project_security([
        {"path": "app/helpers.py", "content": '''
import subprocess


def helper(command: str) -> str:
    subprocess.run(command, shell=True)
    return "done"
'''},
    ])
    assert unsafe["passed"] is False
    assert unsafe["diagnostics"][0]["code"] == "dangerous_process_call"

    safe = validate_project([
        {"path": "app/helpers.py", "content": '''
import subprocess


def helper() -> str:
    try:
        subprocess.run(["fixed-command", "--version"], check=True, timeout=5)
    except OSError:
        pass
    return "done"
'''},
    ], profile="framework")
    assert safe["valid"] is True
    assert "incomplete_component" not in {item["code"] for item in safe["diagnostics"]}
    assert "dangerous_process_call" not in {item["code"] for item in safe["diagnostics"]}
