"""Register the assess_project companion facade."""

import asyncio
from typing import Annotated

from pydantic import Field

from mcp_builder import projects
from mcp_builder.projects.schemas import ProjectAssessmentResult, ProjectFile, ValidationProfile

from .services import Services


def register(mcp, services: Services):
    """Attach the combined static project assessment facade."""
    del services

    @mcp.tool
    async def assess_project(
        files: Annotated[list[ProjectFile], Field(min_length=1, max_length=100)],
        profile: ValidationProfile = "recommended",
    ) -> ProjectAssessmentResult:
        """Inspect, validate, and review security without importing or executing submitted code."""
        return await asyncio.to_thread(projects.assess_project, files, profile)
