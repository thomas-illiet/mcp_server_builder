"""Register the generate_resource MCP tool."""

from mcp_builder.projects import generate_resource as build_resource
from mcp_builder.projects.schemas import GenerationResult, ResourceSpec

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    def generate_resource(specification: ResourceSpec) -> GenerationResult:
        """Generate one safe, typed resource module and its in-memory client test."""
        return build_resource(specification)
