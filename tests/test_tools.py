"""Exercise public tools and schemas through the in-memory FastMCP client."""

import pytest
from fastmcp import Client

from mcp_builder.search.embedding import EmbeddingUnavailableError
from mcp_builder.server import create_server


class ToolStore:
    """Minimal injected document service for transport-level tool tests."""

    def search(self, query, k, source, version, mode):
        """Return an empty envelope or simulate unavailable semantic search."""
        del query, k, source, version
        if mode == "semantic":
            raise EmbeddingUnavailableError("offline")
        return {"results": [], "requested_mode": mode, "effective_mode": mode,
                "fallback_used": False, "warnings": []}

    def status(self):
        """Return a bounded status payload."""
        return {"integrity": "verified_at_startup"}

    def read(self, *args, **kwargs):
        """Satisfy registration tests without accessing documents."""
        del args, kwargs
        return {"content": "test"}


def _data(result):
    """Normalize FastMCP's structured Root model for assertions."""
    if result.structured_content is not None:
        return result.structured_content
    data = result.data
    while hasattr(data, "root"):
        data = data.root
    return data.model_dump() if hasattr(data, "model_dump") else data


@pytest.mark.asyncio
async def test_new_tools_are_published_with_structured_schemas_and_callable():
    """Every companion generator is discoverable and works through MCP transport."""
    async with Client(create_server(ToolStore())) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        expected = {
            "get_builder_guide", "generate_tool", "generate_resource", "generate_prompt",
            "generate_component_test", "inspect_project", "propose_project_patch",
            "review_project_security",
        }
        assert expected <= tools.keys()
        assert tools["generate_tool"].output_schema["type"] == "object"

        guide = await client.call_tool("get_builder_guide", {})
        guide_data = _data(guide)
        assert "Mandatory MCP Builder workflow" in guide_data["guide"]
        assert guide_data["required_tool_workflow"][0]["tools"] == ["get_doc_status"]
        assert guide_data["required_tool_workflow"][-1] == {
            "step": 6, "tools": ["validate_project"], "required": True,
        }
        generated = await client.call_tool("generate_tool", {"specification": {
            "name": "lookup", "description": "Look up a value.", "parameters": [],
            "return_type": "str", "is_async": True,
        }})
        assert _data(generated)["files"][0]["path"] == "app/tools/lookup.py"

        resource = await client.call_tool("generate_resource", {"specification": {
            "name": "record", "uri": "record://item", "parameters": [],
            "return_type": "dict", "is_async": False,
        }})
        assert _data(resource)["files"][0]["path"] == "app/resources/record.py"

        prompt = await client.call_tool("generate_prompt", {"specification": {
            "name": "explain", "description": "Explain a topic.", "arguments": [],
            "is_async": False,
        }})
        assert _data(prompt)["files"][0]["path"] == "app/prompts/explain.py"

        test = await client.call_tool("generate_component_test", {
            "kind": "prompt", "specification": {
                "name": "explain", "description": "Explain a topic.", "arguments": [],
            },
        })
        assert [item["path"] for item in _data(test)["files"]] == ["tests/test_explain.py"]

        project_files = [
            {"path": "app/tools/__init__.py", "content": "from . import ping as ping\n"},
            {"path": "app/tools/ping.py", "content": (
                "from app.instance import mcp\n@mcp.tool\n"
                "def ping() -> str:\n    return 'pong'\n"
            )},
        ]
        inspection = await client.call_tool("inspect_project", {"files": project_files})
        assert _data(inspection)["architecture"]["component_counts"]["tool"] == 1

        patch = await client.call_tool("propose_project_patch", {
            "kind": "tool",
            "specification": {"name": "lookup", "description": "Look up a value.",
                              "parameters": [], "return_type": "str", "is_async": False},
            "files": project_files,
        })
        assert any(item["path"] == "app/tools/lookup.py"
                   for item in _data(patch)["changes"])

        security = await client.call_tool("review_project_security", {
            "files": project_files,
        })
        assert _data(security)["passed"] is True


@pytest.mark.asyncio
async def test_search_docs_schema_and_semantic_error_are_actionable():
    """Search publishes an envelope and maps only endpoint failures to a short ToolError."""
    async with Client(create_server(ToolStore())) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        properties = tools["search_docs"].output_schema["properties"]
        assert {"results", "requested_mode", "effective_mode", "fallback_used", "warnings"} \
            <= properties.keys()
        result = await client.call_tool("search_docs", {"query": "tool", "mode": "lexical"})
        assert _data(result)["results"] == []
        assert _data(result)["schema_version"] == "1"
        with pytest.raises(Exception, match="lexical or hybrid"):
            await client.call_tool("search_docs", {"query": "tool", "mode": "semantic"})
