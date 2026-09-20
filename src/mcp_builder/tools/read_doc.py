"""Register the read_doc MCP tool."""
import asyncio
from typing import Annotated

from pydantic import Field

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    async def read_doc(
        doc_id: Annotated[str, Field(min_length=1, max_length=512)],
        section: Annotated[str, Field(max_length=1000)] | None = None,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=24000)] = 12000,
    ) -> dict:
        """Read a local page or exact section returned by search_docs. Pagination uses characters."""
        return await asyncio.to_thread(services.documents().read, doc_id, section, offset, limit)
