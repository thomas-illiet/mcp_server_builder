"""Register the inspect_project MCP tool."""

import asyncio
from typing import Annotated

from pydantic import Field

from mcp_builder.projects import inspect_project as inspect_files
from mcp_builder.projects.schemas import InspectionResult, ProjectFile

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    async def inspect_project(
        files: Annotated[list[ProjectFile], Field(min_length=1, max_length=100)],
    ) -> InspectionResult:
        """Map an existing FastMCP project statically without importing or executing it."""
        payload = [item.model_dump() for item in files]
        return await asyncio.to_thread(inspect_files, payload)
