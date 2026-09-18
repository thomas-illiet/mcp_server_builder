"""Register all tools explicitly without global server instances."""
from . import (
    generate_component_test,
    generate_project,
    generate_prompt,
    generate_resource,
    generate_tool,
    get_builder_guide,
    get_doc_status,
    get_example,
    inspect_project,
    list_templates,
    propose_project_patch,
    read_doc,
    review_project_security,
    search_docs,
    validate_project,
)
from .services import Services


def register_tools(mcp, services: Services):
    """Attach all public tools in a stable order."""
    search_docs.register(mcp, services)
    read_doc.register(mcp, services)
    get_doc_status.register(mcp, services)
    list_templates.register(mcp, services)
    generate_project.register(mcp, services)
    get_example.register(mcp, services)
    validate_project.register(mcp, services)
    get_builder_guide.register(mcp, services)
    generate_tool.register(mcp, services)
    generate_resource.register(mcp, services)
    generate_prompt.register(mcp, services)
    generate_component_test.register(mcp, services)
    inspect_project.register(mcp, services)
    propose_project_patch.register(mcp, services)
    review_project_security.register(mcp, services)
