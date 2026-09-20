"""Register the assess_readiness companion facade."""

import asyncio
from typing import Annotated

from pydantic import Field

from mcp_builder import projects
from mcp_builder.projects.schemas import (
    ProjectBlueprint,
    ProjectFile,
    ReadinessResult,
    ValidationProfile,
    VerificationOutcome,
)

from .services import Services


def register(mcp, services: Services):
    """Attach the final stateless readiness facade."""
    del services

    @mcp.tool
    async def assess_readiness(
        blueprint: ProjectBlueprint,
        files: Annotated[list[ProjectFile], Field(min_length=1, max_length=100)],
        verification_results: Annotated[
            list[VerificationOutcome], Field(min_length=1, max_length=30)
        ],
        profile: ValidationProfile = "recommended",
    ) -> ReadinessResult:
        """Combine static analysis with bounded results reported by OpenCode."""
        return await asyncio.to_thread(
            projects.assess_readiness, blueprint, files, verification_results, profile
        )
