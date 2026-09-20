"""Prove both base architectures accept every MCP primitive through the companion."""

import subprocess
import sys

import pytest

from mcp_builder.projects.companion import generate_from_blueprint
from mcp_builder.projects.schemas import ProjectBlueprint


@pytest.mark.parametrize("template", ["minimal", "structured"])
@pytest.mark.parametrize("kind", ["tool", "resource", "prompt"])
def test_each_template_accepts_and_discovers_each_primitive(tmp_path, template, kind):
    """Adding any primitive keeps generated imports, lint, and discovery functional."""
    component = {
        "tool": {
            "name": "lookup",
            "description": "Return one known value.",
            "parameters": [],
            "return_type": "str",
        },
        "resource": {
            "name": "lookup",
            "uri": "lookup://current",
            "parameters": [],
            "return_type": "str",
        },
        "prompt": {
            "name": "lookup",
            "description": "Return one known prompt.",
            "arguments": [],
        },
    }[kind]
    blueprint = ProjectBlueprint.model_validate({
        "name": f"{template}_{kind}_server",
        "objective": f"Expose one deterministic {kind} through the {template} template.",
        "template": template,
        f"{kind}s": [component],
        "test_scenarios": [{
            "name": "lookup_success",
            "component_kind": kind,
            "component_name": "lookup",
            "description": "Return the known result.",
            "arguments": {},
            "expected_outcome": "success",
            "result_expectation": {
                "path": ["data"],
                "operator": "equals",
                "value": "ok",
            },
            "assertions": ["The logical result equals ok."],
        }],
    })
    generated = generate_from_blueprint(blueprint)
    assert generated.status == "incomplete"
    for item in generated.files:
        target = tmp_path / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8", newline="\n")

    lint = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr

    assertion = {
        "tool": 'assert "lookup" in {item.name for item in await client.list_tools()}',
        "resource": (
            'assert "lookup://current" in '
            "{str(item.uri) for item in await client.list_resources()}"
        ),
        "prompt": 'assert "lookup" in {item.name for item in await client.list_prompts()}',
    }[kind]
    program = f'''import asyncio
from fastmcp import Client
from app.server import mcp

async def main():
    async with Client(mcp) as client:
        {assertion}

asyncio.run(main())
'''
    discovery = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert discovery.returncode == 0, discovery.stdout + discovery.stderr
