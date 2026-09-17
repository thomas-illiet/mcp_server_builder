"""Register the seven tools explicitly without global server instances."""
from . import (
    generate_project,
    get_doc_status,
    get_example,
    list_templates,
    read_doc,
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
