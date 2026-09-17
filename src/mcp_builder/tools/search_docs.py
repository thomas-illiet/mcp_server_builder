"""Register the search_docs MCP tool."""
import asyncio
from typing import Annotated, Literal

from pydantic import Field

from .services import Services


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    async def search_docs(
        query: Annotated[str, Field(min_length=1, max_length=4000)],
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        source: Literal["fastmcp", "mcp"] | None = None,
        version: Annotated[str, Field(max_length=80)] | None = None,
        mode: Literal["hybrid", "lexical", "semantic"] = "hybrid",
    ) -> list[dict]:
        """Search local official docs. French questions are supported by semantic/hybrid mode."""
        return await asyncio.to_thread(services.documents().search, query, k, source, version, mode)
