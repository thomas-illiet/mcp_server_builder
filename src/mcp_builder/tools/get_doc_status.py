"""Register the get_doc_status MCP tool."""
from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    def get_doc_status() -> dict:
        """Get document dates, versions and startup integrity verification status."""
        return services.documents().status()
