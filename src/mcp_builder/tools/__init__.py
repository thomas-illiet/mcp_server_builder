"""Register all tools explicitly without global server instances."""

import os

from . import (
    assess_project,
    assess_readiness,
    generate_component_test,
    generate_from_blueprint,
    generate_project,
    generate_prompt,
    generate_resource,
    generate_tool,
    get_builder_guide,
    get_design_schema,
    get_doc_status,
    get_example,
    get_verification_plan,
    inspect_project,
    list_templates,
    propose_project_patch,
    read_doc,
    review_project_security,
    search_docs,
    validate_blueprint,
    validate_project,
)
from .services import Services

COMPANION_TOOLS = (
    search_docs,
    read_doc,
    get_doc_status,
    get_design_schema,
    validate_blueprint,
    generate_from_blueprint,
    assess_project,
    get_verification_plan,
    assess_readiness,
)

ADVANCED_TOOLS = (
    get_builder_guide,
    list_templates,
    generate_project,
    get_example,
    validate_project,
    generate_tool,
    generate_resource,
    generate_prompt,
    generate_component_test,
    inspect_project,
    propose_project_patch,
    review_project_security,
)


def register_tools(mcp, services: Services, profile: str | None = None):
    """Attach the compact companion set or the complete advanced set in stable order."""
    selected = (profile or os.getenv("MCP_BUILDER_TOOL_PROFILE", "companion")).strip().lower()
    if selected not in {"companion", "advanced"}:
        raise ValueError("MCP_BUILDER_TOOL_PROFILE must be companion or advanced")
    modules = COMPANION_TOOLS if selected == "companion" else (*COMPANION_TOOLS, *ADVANCED_TOOLS)
    for module in modules:
        module.register(mcp, services)
