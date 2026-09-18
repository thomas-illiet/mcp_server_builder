"""Register the generate_tool MCP tool."""

from mcp_builder.projects import generate_tool as build_tool
from mcp_builder.projects.schemas import GenerationResult, ToolSpec

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    def generate_tool(specification: ToolSpec) -> GenerationResult:
        """Generate one safe, typed tool module and its in-memory client test."""
        return build_tool(specification)
