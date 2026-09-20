"""Register the validate_project MCP tool."""
import asyncio
from typing import Annotated

from pydantic import Field

from mcp_builder import projects
from mcp_builder.projects.schemas import ProjectFile, ValidationProfile, ValidationResult

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    async def validate_project(
        files: Annotated[list[ProjectFile], Field(min_length=1, max_length=100)],
        profile: ValidationProfile = "recommended",
    ) -> ValidationResult:
        """Check Python/TOML and common FastMCP declarations without executing submitted code."""
        result = await asyncio.to_thread(
            projects.validate_project, [item.model_dump() for item in files], profile
        )
        return ValidationResult.model_validate(result)
