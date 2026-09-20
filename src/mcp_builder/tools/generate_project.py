"""Register the generate_project MCP tool."""
from typing import Annotated, Literal

from pydantic import Field

from mcp_builder import projects

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    def generate_project(
        name: Annotated[str, Field(min_length=1, max_length=64)],
        template: Literal["minimal", "structured"] = "structured",
        transport: Literal["http", "stdio"] = "http",
    ) -> dict:
        """Return project files for the client to write. Does not create server-side files."""
        return projects.generate_project(name, template, transport)
