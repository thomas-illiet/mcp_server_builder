"""Register the search_docs MCP tool."""
import asyncio
from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION
from mcp_builder.search.embedding import EmbeddingUnavailableError

from .services import Services


class SearchResult(BaseModel):
    """One ranked documentation passage with its official reference."""

    id: int
    doc_id: str
    title: str
    section: str
    source: str
    version: str
    url: str
    score: float
    snippet: str


class SearchResponse(BaseModel):
    """Expose the requested and effective retrieval strategies."""

    schema_version: str = SCHEMA_VERSION
    server_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    results: list[SearchResult]
    requested_mode: Literal["hybrid", "lexical", "semantic"]
    effective_mode: Literal["hybrid", "lexical", "semantic"]
    fallback_used: bool
    warnings: list[str]


def register(mcp, services: Services):
    """Attach the tool to this server using its injected services."""
    @mcp.tool
    async def search_docs(
        query: Annotated[str, Field(min_length=1, max_length=4000)],
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        source: Literal["fastmcp", "mcp"] | None = None,
        version: Annotated[str, Field(max_length=80)] | None = None,
        mode: Literal["hybrid", "lexical", "semantic"] = "hybrid",
    ) -> SearchResponse:
        """Search the bundled official documentation before designing or generating MCP code."""
        try:
            result = await asyncio.to_thread(
                services.documents().search, query, k, source, version, mode
            )
        except EmbeddingUnavailableError as exc:
            raise ToolError(
                "Semantic search is unavailable. Retry in lexical or hybrid mode."
            ) from exc
        return SearchResponse.model_validate(result)
