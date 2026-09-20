"""Exercise bounded companion inputs that previously escaped the common envelope."""

from mcp_builder.projects.companion import (
    assess_project,
    assess_readiness,
    generate_from_blueprint,
    get_verification_plan,
    validate_blueprint,
)
from mcp_builder.projects.schemas import ProjectBlueprint


def _simple_blueprint(**updates) -> ProjectBlueprint:
    """Return a complete single-tool contract for boundary tests."""
    payload = {
        "name": "bounded_server",
        "objective": "Expose one deterministic bounded result through FastMCP.",
        "tools": [{
            "name": "lookup",
            "description": "Return one bounded result.",
            "parameters": [],
            "return_type": "str",
        }],
        "test_scenarios": [{
            "name": "lookup_success",
            "component_kind": "tool",
            "component_name": "lookup",
            "description": "Return the known bounded result.",
            "arguments": {},
            "expected_outcome": "success",
            "result_expectation": {
                "path": ["data"],
                "operator": "equals",
                "value": "ok",
            },
            "assertions": ["The result equals ok."],
        }],
    }
    payload.update(updates)
    return ProjectBlueprint.model_validate(payload)


def test_conflicting_type_definitions_return_blocked_envelopes():
    """A blueprint rejected by validation cannot crash later companion facades."""
    blueprint = _simple_blueprint(
        schemas=[{
            "kind": "object",
            "name": "Result",
            "fields": [{
                "name": "value",
                "type": "str",
                "description": "Returned value.",
            }],
        }],
        tools=[{
            "name": "lookup",
            "description": "Return one conflicting result.",
            "parameters": [],
            "return_type": "Result",
            "definitions": [{
                "kind": "enum",
                "name": "Result",
                "values": ["ok"],
            }],
        }],
    )

    validation = validate_blueprint(blueprint)
    generation = generate_from_blueprint(blueprint)
    plan = get_verification_plan(blueprint)

    assert validation.status == "invalid"
    assert "invalid_component_contract" in {
        item.code for item in validation.blocking_issues
    }
    assert generation.status == "blocked"
    assert generation.files == []
    assert plan.status == "blocked"
    assert plan.checks == []


def test_invalid_paths_return_a_blocked_assessment_envelope():
    """Duplicate paths remain ordinary diagnostics instead of raising ValueError."""
    files = [
        {"path": "app/server.py", "content": "value = 1\n"},
        {"path": "app/server.py", "content": "value = 2\n"},
    ]
    result = assess_project(files)

    assert result.status == "blocked"
    assert result.static_valid is False
    assert "invalid_path" in {item.code for item in result.blocking_issues}


def test_aggregate_size_limit_blocks_assessment_and_readiness():
    """Two individually valid files above the aggregate cap return typed envelopes."""
    files = [
        {"path": "first.txt", "content": "a" * 600_000},
        {"path": "second.txt", "content": "b" * 600_000},
    ]

    assessment = assess_project(files)
    readiness = assess_readiness(_simple_blueprint(), files, [])

    assert assessment.status == "blocked"
    assert readiness.status == "blocked"
    assert readiness.ready is False
    assert {item.code for item in assessment.blocking_issues} == {
        "project_size_limit"
    }
    assert {item.code for item in readiness.blocking_issues} == {
        "project_size_limit"
    }
