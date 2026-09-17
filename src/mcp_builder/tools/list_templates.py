"""Register the list_templates MCP tool."""
from mcp_builder import projects

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    def list_templates() -> list[dict]:
        """List the deterministic project templates and accepted parameters."""
        return projects.list_templates()
