"""Register the get_verification_plan companion facade."""

from mcp_builder import projects
from mcp_builder.projects.schemas import ProjectBlueprint, VerificationPlanResult

from .services import Services


def register(mcp, services: Services):
    """Attach the non-executing verification-plan facade."""
    del services

    @mcp.tool
    def get_verification_plan(blueprint: ProjectBlueprint) -> VerificationPlanResult:
        """Return the build, test, MCP, Docker, and OpenCode checks the caller must execute."""
        return projects.get_verification_plan(blueprint)
