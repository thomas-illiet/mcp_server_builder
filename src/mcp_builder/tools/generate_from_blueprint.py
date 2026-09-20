"""Register the generate_from_blueprint companion facade."""

from mcp_builder import projects
from mcp_builder.projects.schemas import BlueprintGenerationResult, ProjectBlueprint

from .services import Services


def register(mcp, services: Services):
    """Attach the in-memory blueprint generator."""
    del services

    @mcp.tool
    def generate_from_blueprint(blueprint: ProjectBlueprint) -> BlueprintGenerationResult:
        """Generate project files for OpenCode to write; never write or execute server-side."""
        return projects.generate_from_blueprint(blueprint)
