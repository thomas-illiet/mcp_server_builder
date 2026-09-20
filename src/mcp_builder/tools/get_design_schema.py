"""Register the get_design_schema companion facade."""

from mcp_builder import projects
from mcp_builder.projects.schemas import DesignSchemaResult

from .services import Services


def register(mcp, services: Services):
    """Attach the stateless design-schema facade."""
    del services

    @mcp.tool
    def get_design_schema() -> DesignSchemaResult:
        """Return every bounded decision needed to design a FastMCP project for OpenCode."""
        return projects.get_design_schema()
