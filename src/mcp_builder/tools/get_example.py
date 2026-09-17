"""Register the get_example MCP tool."""
from typing import Literal

from mcp_builder import projects

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    def get_example(topic: Literal["tool", "resource", "prompt", "context", "errors", "testing"]) -> dict:
        """Get a tested FastMCP example and its official documentation reference."""
        return projects.get_example(topic)
