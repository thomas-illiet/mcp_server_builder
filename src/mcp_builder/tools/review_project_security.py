"""Register the review_project_security MCP tool."""

import asyncio
from typing import Annotated

from pydantic import Field

from mcp_builder.projects import review_project_security as review_security
from mcp_builder.projects.schemas import ProjectFile, SecurityReview

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    del services

    @mcp.tool
    async def review_project_security(
        files: Annotated[list[ProjectFile], Field(min_length=1, max_length=100)],
    ) -> SecurityReview:
        """Review high-confidence security patterns without importing or running code."""
        payload = [item.model_dump() for item in files]
        result = await asyncio.to_thread(review_security, payload)
        return SecurityReview.model_validate(result)
