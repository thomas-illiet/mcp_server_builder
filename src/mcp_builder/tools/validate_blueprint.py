"""Register the validate_blueprint companion facade."""

from mcp_builder import projects
from mcp_builder.projects.schemas import BlueprintValidationResult, ProjectBlueprint

from .services import Services


def register(mcp, services: Services):
    """Attach the stateless blueprint-validation facade."""
    del services

    @mcp.tool
    def validate_blueprint(blueprint: ProjectBlueprint) -> BlueprintValidationResult:
        """Validate design completeness and cross-field contracts without executing code."""
        return projects.validate_blueprint(blueprint)
