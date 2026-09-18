"""Register the generate_prompt MCP tool."""

from mcp_builder.projects import generate_prompt as build_prompt
from mcp_builder.projects.schemas import GenerationResult, PromptSpec

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    def generate_prompt(specification: PromptSpec) -> GenerationResult:
        """Generate one safe, typed prompt module and its in-memory client test."""
        return build_prompt(specification)
