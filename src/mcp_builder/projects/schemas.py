"""Bounded MCP payloads used for static project validation."""
from pydantic import BaseModel, Field


class ProjectFile(BaseModel):
    """Bounded in-memory file payload for static validation; never persisted by the server."""
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=1_000_000)
