"""Exercise the stateless OpenCode companion facades and tool profiles."""

from pathlib import Path

import pytest
from fastmcp import Client
from pydantic import ValidationError

from mcp_builder.projects import (
    assess_project,
    assess_readiness,
    generate_from_blueprint,
    generate_project,
    get_design_schema,
    get_verification_plan,
    validate_blueprint,
)
from mcp_builder.projects.schemas import (
    ComponentParameter,
    ProjectBlueprint,
    PromptSpec,
    ResourceSpec,
    ToolSpec,
    VerificationOutcome,
)
from mcp_builder.server import create_server


class CompanionStore:
    """Small document service used only to enumerate profile-specific tools."""

    def search(self, query, k, source, version, mode):
        """Return an empty lexical result."""
        del query, k, source, version
        return {
            "results": [],
            "requested_mode": mode,
            "effective_mode": mode,
            "fallback_used": False,
            "warnings": [],
        }

    def status(self):
        """Return deterministic corpus status."""
        return {"integrity": "verified_at_startup"}

    def read(self, *args, **kwargs):
        """Return a bounded document response."""
        del args, kwargs
        return {"content": "test"}


def _blueprint(**updates) -> ProjectBlueprint:
    """Return one complete blueprint suitable for facade tests."""
    payload = {
        "name": "weather_server",
        "objective": "Expose a deterministic city weather lookup to OpenCode.",
        "tools": [{
            "name": "weather",
            "description": "Return weather for one city.",
            "parameters": [{
                "name": "city",
                "type": "str",
                "description": "City to inspect.",
            }],
            "return_type": "str",
            "is_async": True,
        }],
        "annotations": [{
            "component_kind": "tool",
            "component_name": "weather",
            "read_only": True,
            "destructive": False,
            "idempotent": True,
            "open_world": True,
        }],
        "test_scenarios": [{
            "name": "weather_success",
            "component_kind": "tool",
            "component_name": "weather",
            "description": "Return structured weather for a known city.",
            "arguments": {"city": "Paris"},
            "expected_outcome": "success",
            "result_expectation": {
                "path": ["data"], "operator": "contains", "value": "Paris",
            },
            "assertions": ["The result identifies Paris."],
        }],
    }
    payload.update(updates)
    return ProjectBlueprint.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ProjectBlueprint, {
            "name": "class",
            "objective": "Reject a Python keyword as the project identifier.",
        }),
        (ComponentParameter, {
            "name": "class", "type": "str", "description": "Invalid parameter.",
        }),
        (ToolSpec, {
            "name": "class", "description": "Invalid tool.", "return_type": "str",
        }),
        (ResourceSpec, {
            "name": "class", "uri": "config://value", "return_type": "str",
        }),
        (PromptSpec, {
            "name": "class", "description": "Invalid prompt.",
        }),
    ],
)
def test_python_identifiers_reject_keywords_during_schema_validation(model, payload):
    """Generated modules, functions, and parameters must never use Python keywords."""
    with pytest.raises(ValidationError, match="must not be keywords"):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
@pytest.mark.parametrize("location", ["arguments", "result_expectation"])
def test_blueprint_rejects_non_finite_json_values_recursively(bad_value, location):
    """NaN and infinities cannot enter nested scenario inputs or expected results."""
    scenario = {
        "name": "calculate_success",
        "component_kind": "tool",
        "component_name": "calculate",
        "description": "Calculate one finite structured result.",
        "arguments": {"payload": {"values": [1.0]}},
        "expected_outcome": "success",
        "result_expectation": {
            "path": ["data"],
            "operator": "equals",
            "value": {"values": [1.0]},
        },
        "assertions": ["The result contains only finite values."],
    }
    if location == "arguments":
        scenario["arguments"] = {"payload": {"values": [bad_value]}}
    else:
        scenario["result_expectation"]["value"] = {"values": [bad_value]}

    with pytest.raises(ValidationError, match="finite floats"):
        ProjectBlueprint.model_validate({
            "name": "calculator",
            "objective": "Calculate and return one structured numeric result.",
            "tools": [{
                "name": "calculate",
                "description": "Calculate one structured result.",
                "parameters": [{
                    "name": "payload",
                    "type": "dict",
                    "description": "Finite numeric inputs.",
                }],
                "return_type": "dict",
            }],
            "test_scenarios": [scenario],
        })


def test_finite_nested_json_values_validate_and_generate():
    """Finite nested inputs and expectations remain valid and serializable in generated tests."""
    blueprint = ProjectBlueprint.model_validate({
        "name": "calculator",
        "objective": "Calculate and return one structured numeric result.",
        "tools": [{
            "name": "calculate",
            "description": "Calculate one structured result.",
            "parameters": [{
                "name": "payload",
                "type": "dict",
                "description": "Finite numeric inputs.",
            }],
            "return_type": "dict",
        }],
        "annotations": [{
            "component_kind": "tool",
            "component_name": "calculate",
            "read_only": True,
            "destructive": False,
            "idempotent": True,
            "open_world": False,
        }],
        "test_scenarios": [{
            "name": "calculate_success",
            "component_kind": "tool",
            "component_name": "calculate",
            "description": "Calculate one finite structured result.",
            "arguments": {"payload": {"values": [-2.5, 0.0, 3.75]}},
            "expected_outcome": "success",
            "result_expectation": {
                "path": ["data"],
                "operator": "equals",
                "value": {"total": 1.25},
            },
            "assertions": ["The result total equals 1.25."],
        }],
    })
    assert validate_blueprint(blueprint).valid is True
    generated = generate_from_blueprint(blueprint)
    assert generated.status == "incomplete"
    smoke = next(item.content for item in generated.files if item.path == "tests/test_smoke.py")
    assert "-2.5" in smoke
    assert "1.25" in smoke


def test_design_schema_exposes_all_decisions_and_common_envelope():
    """The first facade is self-describing and uses the shared versioned envelope."""
    result = get_design_schema()
    properties = result.blueprint_schema["properties"]
    assert {
        "objective", "transport", "client_profile", "tools", "resources", "prompts",
        "schemas", "annotations", "secrets", "data_sources", "errors", "test_scenarios",
    } <= properties.keys()
    assert result.status == "ok"
    assert result.schema_version == "1"
    assert result.blocking_issues == []
    assert result.next_actions[0].tool == "validate_blueprint"


def test_blueprint_cannot_generate_more_files_than_assessment_accepts():
    """The facade can always re-ingest every project it agrees to generate."""
    with pytest.raises(ValidationError, match="40 total primitives"):
        ProjectBlueprint.model_validate({
            "name": "oversized",
            "objective": "Expose an intentionally oversized collection of small tools.",
            "tools": [
                {
                    "name": f"tool_{index}",
                    "description": "Return one value.",
                    "parameters": [],
                    "return_type": "str",
                }
                for index in range(41)
            ],
        })


def test_blueprint_validation_requires_components_scenarios_and_safe_secrets():
    """Cross-field omissions return actionable issues instead of generating partial code."""
    missing = validate_blueprint(ProjectBlueprint(
        name="empty_server",
        objective="Describe an intentionally empty server contract.",
    ))
    assert missing.status == "invalid"
    assert {item.code for item in missing.blocking_issues} == {"missing_component"}

    unsafe = _blueprint(
        tools=[ToolSpec(
            name="weather",
            description="Return weather for one city.",
            parameters=[{
                "name": "api_key",
                "type": "str",
                "description": "Unsafe caller-provided secret.",
            }],
            return_type="str",
        )],
        test_scenarios=[],
    )
    result = validate_blueprint(unsafe)
    assert result.valid is False
    assert {item.code for item in result.blocking_issues} >= {
        "missing_test_scenario", "secret_in_mcp_input",
    }


def test_named_types_are_closed_and_blueprint_generation_stays_in_memory(tmp_path, monkeypatch):
    """Structured types are allowed, code fragments are rejected, and no file is written."""
    with pytest.raises(ValidationError):
        ToolSpec(
            name="unsafe",
            description="Reject arbitrary annotations.",
            parameters=[],
            return_type="os.system('whoami')",
        )
    with pytest.raises(ValidationError):
        ProjectBlueprint(
            name="unsafe_type",
            objective="Reject a Python constant used as a generated class name.",
            schemas=[{"kind": "object", "name": "None", "fields": [{
                "name": "value", "type": "str", "description": "A value.",
            }]}],
        )

    blueprint = _blueprint(
        schemas=[{
            "kind": "object",
            "name": "WeatherResult",
            "fields": [{
                "name": "temperature",
                "type": "float",
                "description": "Measured temperature.",
            }],
        }],
        tools=[{
            "name": "weather",
            "description": "Return weather for one city.",
            "parameters": [{
                "name": "city",
                "type": "str",
                "description": "City to inspect.",
            }],
            "return_type": "WeatherResult",
            "is_async": True,
        }],
        test_scenarios=[{
            "name": "weather_success",
            "component_kind": "tool",
            "component_name": "weather",
            "description": "Return structured weather for a known city.",
            "arguments": {"city": "Paris"},
            "expected_outcome": "success",
            "result_expectation": {
                "path": ["data"],
                "operator": "equals",
                "value": {"temperature": 20.0},
            },
            "assertions": ["The result contains the measured temperature."],
        }],
    )
    monkeypatch.chdir(tmp_path)
    result = generate_from_blueprint(blueprint)
    paths = {item.path for item in result.files}
    assert result.status == "incomplete"
    assert "app/tools/weather.py" in paths
    assert "tests/test_weather.py" in paths
    assert "app/tools/add.py" not in paths
    assert "app/resources/version.py" not in paths
    assert "app/prompts/explain.py" not in paths
    weather = next(item.content for item in result.files if item.path == "app/tools/weather.py")
    assert "'readOnlyHint': True" in weather
    assert "'destructiveHint': False" in weather
    assert list(Path(tmp_path).iterdir()) == []
    assert result.executed is False


def test_verification_plan_is_explicit_and_todo_project_is_never_ready():
    """Only OpenCode executes checks, and reported passes cannot hide TODO skeletons."""
    blueprint = _blueprint()
    generated = generate_from_blueprint(blueprint)
    assessment = assess_project([item.model_dump() for item in generated.files])
    assert assessment.status == "incomplete"
    assert assessment.static_valid is True
    assert assessment.static_ready is False
    assert assessment.executed is False
    plan = get_verification_plan(blueprint)
    check_ids = {item.check_id for item in plan.checks}
    assert {
        "lock", "install", "lint", "unit_tests", "mcp_smoke", "http_transport",
        "docker_build", "docker_runtime", "opencode_connection", "opencode_invocation",
    } <= check_ids
    assert plan.executed is False

    outcomes = [
        VerificationOutcome(check_id=item.check_id, status="passed", exit_code=0)
        for item in plan.checks
    ]
    readiness = assess_readiness(
        blueprint,
        [item.model_dump() for item in generated.files],
        outcomes,
    )
    assert readiness.ready is False
    assert readiness.status in {"incomplete", "blocked"}
    assert readiness.executed is False


def test_readiness_rejects_a_different_project_even_when_checks_are_reported_passed():
    """Runtime claims cannot make an unrelated MCP surface satisfy the blueprint."""
    blueprint = _blueprint()
    unrelated = generate_project("unrelated", "structured", "http")["files"]
    plan = get_verification_plan(blueprint)
    outcomes = [
        VerificationOutcome(check_id=item.check_id, status="passed", exit_code=0)
        for item in plan.checks
    ]
    result = assess_readiness(blueprint, unrelated, outcomes)
    assert result.ready is False
    assert result.status == "blocked"
    codes = {item.code for item in result.blocking_issues}
    assert "blueprint_component_missing" in codes
    assert "blueprint_component_unexpected" in codes


def test_non_tool_behavior_annotations_are_rejected():
    """Tool behavior hints are not silently emitted on resources or prompts."""
    blueprint = ProjectBlueprint.model_validate({
        "name": "resource_server",
        "objective": "Expose one annotated configuration resource safely.",
        "resources": [{
            "name": "configuration",
            "uri": "config://current",
            "parameters": [],
            "return_type": "str",
        }],
        "annotations": [{
            "component_kind": "resource",
            "component_name": "configuration",
            "read_only": True,
        }],
        "test_scenarios": [{
            "name": "configuration_success",
            "component_kind": "resource",
            "component_name": "configuration",
            "description": "Read the current configuration.",
                "arguments": {},
                "expected_outcome": "success",
                "result_expectation": {
                    "path": ["data"], "operator": "contains", "value": "configuration",
                },
                "assertions": ["The resource contains configuration text."],
        }],
    })
    result = validate_blueprint(blueprint)
    assert result.valid is False
    assert "unsupported_component_annotations" in {
        item.code for item in result.blocking_issues
    }


def test_blueprint_scenarios_validate_types_and_cover_error_contracts():
    """Generated calls cannot carry invalid JSON types or omit a declared failure path."""
    wrong_type = _blueprint(test_scenarios=[{
        "name": "weather_success",
        "component_kind": "tool",
        "component_name": "weather",
        "description": "Call weather with an invalid city value.",
        "arguments": {"city": 42},
        "expected_outcome": "success",
        "result_expectation": {
            "path": ["data"], "operator": "contains", "value": "Paris",
        },
        "assertions": ["The result identifies the city."],
    }])
    result = validate_blueprint(wrong_type)
    assert "scenario_argument_type_mismatch" in {
        item.code for item in result.blocking_issues
    }

    uncovered_error = _blueprint(errors=[{
        "component_kind": "tool",
        "component_name": "weather",
        "code": "unknown_city",
        "condition": "The requested city is absent.",
        "message": "The requested city is unknown.",
    }])
    result = validate_blueprint(uncovered_error)
    assert "missing_error_test_scenario" in {
        item.code for item in result.blocking_issues
    }


def test_scenarios_require_machine_checkable_result_or_exception_expectations():
    """Free-form assertion prose alone cannot define readiness evidence."""
    payload = _blueprint().model_dump()
    payload["test_scenarios"][0]["result_expectation"] = None
    with pytest.raises(ValidationError, match="result_expectation"):
        ProjectBlueprint.model_validate(payload)

    payload["test_scenarios"] = [{
        "name": "weather_error",
        "component_kind": "tool",
        "component_name": "weather",
        "description": "Reject an unknown city.",
        "arguments": {"city": "Atlantis"},
        "expected_outcome": "error",
        "error_code": "unknown_city",
        "assertions": ["The declared error is raised."],
    }]
    with pytest.raises(ValidationError, match="expected_exception"):
        ProjectBlueprint.model_validate(payload)


def test_readiness_aligns_types_hints_and_each_scenario_with_blueprint():
    """Reported green commands cannot hide a drifted typed contract or missing hints."""
    blueprint = _blueprint()
    files = [
        {"path": "app/instance.py", "content": (
            "from fastmcp import FastMCP\n\nmcp = FastMCP('weather')\n"
        )},
        {"path": "app/server.py", "content": (
            "from app import tools  # noqa: F401\nfrom app.instance import mcp\n"
        )},
        {"path": "app/tools/__init__.py", "content": (
            "from . import weather as weather\n"
        )},
        {"path": "app/tools/weather.py", "content": '''
from app.instance import mcp


@mcp.tool(annotations={'readOnlyHint': True, 'destructiveHint': False,
                       'idempotentHint': True, 'openWorldHint': True})
async def weather(city: str) -> str:
    """Return weather for one city."""
    return f"Weather for {city}"
'''},
        {"path": "tests/weather_contract.py", "content": '''
from fastmcp import Client

from app.server import mcp


async def test_weather_success_contract_is_implemented():
    async with Client(mcp) as client:
        result = await client.call_tool("weather", {"city": "Paris"})
        assert "Paris" in str(result.data)
'''},
    ]
    outcomes = [
        VerificationOutcome(check_id=item.check_id, status="passed", exit_code=0)
        for item in get_verification_plan(blueprint).checks
        if item.required
    ]
    ready = assess_readiness(blueprint, files, outcomes)
    assert ready.ready is True
    assert ready.status == "ready"

    files[3] = {
        "path": "app/tools/weather.py",
        "content": '''
from app.instance import mcp


@mcp.tool
async def weather(city: int) -> str:
    """Return weather for one city."""
    return str(city)
''',
    }
    drifted = assess_readiness(blueprint, files, outcomes)
    codes = {item.code for item in drifted.blocking_issues}
    assert drifted.ready is False
    assert {"blueprint_parameter_types_mismatch", "blueprint_annotations_mismatch"} <= codes


@pytest.mark.parametrize(
    "assertion",
    [
        "assert result == result",
        'assert "London" in result.data',
    ],
)
def test_readiness_rejects_tautological_or_wrong_result_assertions(assertion):
    """An assertion must bind the call result to the exact structured expectation."""
    blueprint = _blueprint()
    files = [
        {"path": "app/instance.py", "content": (
            "from fastmcp import FastMCP\n\nmcp = FastMCP('weather')\n"
        )},
        {"path": "app/server.py", "content": (
            "from app import tools  # noqa: F401\nfrom app.instance import mcp\n"
        )},
        {"path": "app/tools/__init__.py", "content": "from . import weather as weather\n"},
        {"path": "app/tools/weather.py", "content": '''
from app.instance import mcp


@mcp.tool(annotations={'readOnlyHint': True, 'destructiveHint': False,
                       'idempotentHint': True, 'openWorldHint': True})
async def weather(city: str) -> str:
    """Return weather for one city."""
    return f"Weather for {city}"
'''},
        {"path": "tests/weather_contract.py", "content": f'''
from fastmcp import Client

from app.server import mcp


async def test_weather_success_contract_is_implemented():
    async with Client(mcp) as client:
        result = await client.call_tool("weather", {{"city": "Paris"}})
        {assertion}
'''},
    ]
    outcomes = [
        VerificationOutcome(check_id=item.check_id, status="passed", exit_code=0)
        for item in get_verification_plan(blueprint).checks
        if item.required
    ]
    readiness = assess_readiness(blueprint, files, outcomes)
    assert readiness.ready is False
    assert "blueprint_scenario_unverified" in {
        item.code for item in readiness.blocking_issues
    }


def test_error_scenario_requires_exact_exception_type_and_contract_message():
    """A broad or message-free raises block cannot satisfy an error scenario."""
    blueprint = _blueprint(
        errors=[{
            "component_kind": "tool",
            "component_name": "weather",
            "code": "unknown_city",
            "condition": "The requested city is absent.",
            "message": "The requested city is unknown.",
        }],
        test_scenarios=[{
            "name": "weather_error",
            "component_kind": "tool",
            "component_name": "weather",
            "description": "Reject an unknown city.",
            "arguments": {"city": "Atlantis"},
            "expected_outcome": "error",
            "error_code": "unknown_city",
            "expected_exception": "ToolError",
            "assertions": ["The exact user-facing error is raised."],
        }],
    )
    files = [
        {"path": "app/instance.py", "content": (
            "from fastmcp import FastMCP\n\nmcp = FastMCP('weather')\n"
        )},
        {"path": "app/server.py", "content": (
            "from app import tools  # noqa: F401\nfrom app.instance import mcp\n"
        )},
        {"path": "app/tools/__init__.py", "content": "from . import weather as weather\n"},
        {"path": "app/tools/weather.py", "content": '''
from fastmcp.exceptions import ToolError

from app.instance import mcp


@mcp.tool(annotations={'readOnlyHint': True, 'destructiveHint': False,
                       'idempotentHint': True, 'openWorldHint': True})
async def weather(city: str) -> str:
    """Return weather for one city."""
    raise ToolError("The requested city is unknown.")
'''},
        {"path": "tests/weather_contract.py", "content": '''
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.server import mcp


async def test_weather_error_contract_is_implemented():
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="The requested city is unknown."):
            await client.call_tool("weather", {"city": "Atlantis"})
'''},
    ]
    outcomes = [
        VerificationOutcome(check_id=item.check_id, status="passed", exit_code=0)
        for item in get_verification_plan(blueprint).checks
        if item.required
    ]
    accepted = assess_readiness(blueprint, files, outcomes)
    assert accepted.ready is True

    files[-1]["content"] = files[-1]["content"].replace(
        'match="The requested city is unknown."', 'match="unknown"'
    )
    rejected = assess_readiness(blueprint, files, outcomes)
    assert rejected.ready is False
    assert "blueprint_scenario_unverified" in {
        item.code for item in rejected.blocking_issues
    }


@pytest.mark.asyncio
async def test_companion_is_default_and_advanced_retains_legacy_tools(monkeypatch):
    """The default profile is compact while advanced remains backward compatible."""
    monkeypatch.delenv("MCP_BUILDER_TOOL_PROFILE", raising=False)
    async with Client(create_server(CompanionStore())) as client:
        companion = {item.name for item in await client.list_tools()}
    assert companion == {
        "search_docs", "read_doc", "get_doc_status", "get_design_schema",
        "validate_blueprint", "generate_from_blueprint", "assess_project",
        "get_verification_plan", "assess_readiness",
    }

    monkeypatch.setenv("MCP_BUILDER_TOOL_PROFILE", "advanced")
    async with Client(create_server(CompanionStore())) as client:
        advanced = {item.name for item in await client.list_tools()}
    assert companion < advanced
    assert {
        "generate_project", "validate_project", "inspect_project", "propose_project_patch",
    } <= advanced
