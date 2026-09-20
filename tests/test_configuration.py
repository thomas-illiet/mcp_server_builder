"""Verify deterministic server-side configuration generation and assessment."""

import ast
import subprocess
import sys

from mcp_builder.projects.companion import assess_readiness, generate_from_blueprint
from mcp_builder.projects.configuration import (
    configuration_issues,
    configuration_requirements,
    extend_env_example,
    render_configuration_module,
    wire_compose,
    wire_server,
)
from mcp_builder.projects.schemas import ProjectBlueprint
from mcp_builder.projects.templates import generate_project


def _configured_blueprint() -> ProjectBlueprint:
    """Return declarations with required, optional, and shared configuration keys."""
    return ProjectBlueprint.model_validate({
        "name": "configured_server",
        "objective": "Expose a configured service without passing credentials over MCP.",
        "secrets": [
            {
                "name": "api token",
                "environment_variable": "SERVICE_TOKEN",
                "description": "Credential used by the upstream service.",
                "required": True,
            },
            {
                "name": "trace token",
                "environment_variable": "TRACE_TOKEN",
                "description": "Optional credential used only for tracing.",
                "required": False,
            },
        ],
        "data_sources": [{
            "name": "catalog",
            "kind": "api",
            "description": "Read the upstream catalog API.",
            "configuration_keys": ["CATALOG_URL", "SERVICE_TOKEN"],
        }],
    })


def test_configuration_generation_enforces_requiredness_without_values():
    """Generated files wire names and requiredness but never contain secret values."""
    requirements = configuration_requirements(_configured_blueprint())
    assert [(item.key, item.required) for item in requirements] == [
        ("CATALOG_URL", True),
        ("SERVICE_TOKEN", True),
        ("TRACE_TOKEN", False),
    ]

    module = render_configuration_module(requirements)
    ast.parse(module)
    assert "os.getenv(name)" in module
    assert "required=True" in module
    assert "required=False" in module
    assert "Credential used by" not in module

    env = extend_env_example("# Server configuration.\n", requirements)
    assert "SERVICE_TOKEN=\n" in env
    assert "TRACE_TOKEN=\n" in env


def test_configuration_assessment_requires_startup_and_compose_wiring():
    """Documentation alone cannot satisfy a blueprint's configuration contract."""
    requirements = configuration_requirements(_configured_blueprint())
    project = generate_project("configured_server", "structured", "http")
    files = {item["path"]: item["content"] for item in project["files"]}
    files["app/config.py"] = render_configuration_module(requirements)
    files["app/server.py"] = wire_server(files["app/server.py"])
    files["compose.yaml"] = wire_compose(files["compose.yaml"], requirements)
    files[".env.example"] = extend_env_example(files[".env.example"], requirements)
    payload = [{"path": path, "content": content} for path, content in files.items()]

    assert configuration_issues(payload, requirements) == []
    assert '${SERVICE_TOKEN:?Set SERVICE_TOKEN in .env}' in files["compose.yaml"]
    assert '${TRACE_TOKEN:-}' in files["compose.yaml"]

    active_compose = files["compose.yaml"]
    files["compose.yaml"] = active_compose.replace(
        '      SERVICE_TOKEN: "${SERVICE_TOKEN:?Set SERVICE_TOKEN in .env}"',
        '      # SERVICE_TOKEN: "${SERVICE_TOKEN:?Set SERVICE_TOKEN in .env}"',
    )
    payload = [{"path": path, "content": content} for path, content in files.items()]
    codes = {item[0] for item in configuration_issues(payload, requirements)}
    assert "blueprint_configuration_compose_missing" in codes
    files["compose.yaml"] = active_compose

    files["app/config.py"] = files["app/config.py"].replace(
        "'SERVICE_TOKEN': _read('SERVICE_TOKEN', required=True)",
        "'SERVICE_TOKEN': _read('SERVICE_TOKEN', required=False)",
    )
    payload = [{"path": path, "content": content} for path, content in files.items()]
    codes = {item[0] for item in configuration_issues(payload, requirements)}
    assert "blueprint_configuration_requiredness_mismatch" in codes


def test_blueprint_facades_generate_and_assess_configuration_wiring(tmp_path):
    """The high-level companion wires declarations and detects later removal."""
    payload = _configured_blueprint().model_dump()
    payload.update({
        "tools": [{
            "name": "catalog_item",
            "description": "Read one catalog item.",
            "parameters": [{
                "name": "item_id",
                "type": "str",
                "description": "Catalog identifier.",
            }],
            "return_type": "str",
        }],
        "test_scenarios": [{
            "name": "catalog_item_success",
            "component_kind": "tool",
            "component_name": "catalog_item",
            "description": "Return the requested catalog item.",
            "arguments": {"item_id": "42"},
            "expected_outcome": "success",
            "result_expectation": {
                "path": ["data"],
                "operator": "contains",
                "value": "42",
            },
            "assertions": ["The result identifies catalog item 42."],
        }],
    })
    blueprint = ProjectBlueprint.model_validate(payload)
    generated = generate_from_blueprint(blueprint)
    files = [item.model_dump() for item in generated.files]
    file_map = {item["path"]: item["content"] for item in files}

    assert "app/config.py" in file_map
    assert "from app.config import settings" in file_map["app/server.py"]
    assert '${CATALOG_URL:?Set CATALOG_URL in .env}' in file_map["compose.yaml"]

    for path, content in file_map.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    clean = assess_readiness(blueprint, files, [])
    assert not {
        item.code for item in clean.blocking_issues
        if item.code.startswith("blueprint_configuration")
    }

    file_map["app/server.py"] = file_map["app/server.py"].replace(
        "from app.config import settings  # noqa: F401\n", ""
    )
    changed = [{"path": path, "content": content} for path, content in file_map.items()]
    broken = assess_readiness(blueprint, changed, [])
    assert "blueprint_configuration_startup_missing" in {
        item.code for item in broken.blocking_issues
    }
