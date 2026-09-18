"""Register the generate_component_test MCP tool."""

from typing import Literal

from mcp_builder.projects import generate_component_test as build_test
from mcp_builder.projects.schemas import GenerationResult, PromptSpec, ResourceSpec, ToolSpec

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    def generate_component_test(
        kind: Literal["tool", "resource", "prompt"],
        specification: ToolSpec | ResourceSpec | PromptSpec,
    ) -> GenerationResult:
        """Generate a targeted test from an existing component specification."""
        return build_test(kind, specification.model_dump())
