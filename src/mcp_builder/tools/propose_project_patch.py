"""Register the propose_project_patch MCP tool."""

import asyncio
from typing import Annotated, Literal

from pydantic import Field

from mcp_builder.projects import propose_project_patch as propose_patch
from mcp_builder.projects.schemas import (
    PatchProposal,
    ProjectFile,
    PromptSpec,
    ResourceSpec,
    ToolSpec,
)

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    async def propose_project_patch(
        kind: Literal["tool", "resource", "prompt"],
        specification: ToolSpec | ResourceSpec | PromptSpec,
        files: Annotated[list[ProjectFile], Field(min_length=1, max_length=100)],
    ) -> PatchProposal:
        """Propose hash-guarded file changes without writing or executing submitted code."""
        payload = [item.model_dump() for item in files]
        return await asyncio.to_thread(
            propose_patch, kind, specification.model_dump(), payload
        )
