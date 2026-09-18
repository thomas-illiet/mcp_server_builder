"""Register the get_builder_guide MCP tool."""

from mcp_builder.projects.guide import get_builder_guide as build_guide

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    def get_builder_guide() -> dict:
        """Return the complete FastMCP builder architecture and safety guide."""
        return build_guide()
