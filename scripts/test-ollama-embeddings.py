"""Explicit integration check against a local Ollama BGE-M3 endpoint."""

import os
import tempfile
from pathlib import Path

from starlette.testclient import TestClient

from mcp_builder.corpus.files import digest, write_json
from mcp_builder.search.embedding import Embedder
from mcp_builder.search.index import build
from mcp_builder.search.store import Store
from mcp_builder.server import create_app


def make_sources(root: Path) -> None:
    """Create a tiny, valid English documentation snapshot."""
    contents = {
        "docs/fastmcp/server.md": "# Server\nFastMCP creates an MCP server in Python.\n",
        "docs/mcp/tools.md": "# Tools\nMCP tools expose functions to clients.\n",
        "indexes/fastmcp.txt": "fastmcp\n",
        "indexes/mcp.txt": "mcp\n",
    }
    for name, content in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    write_json(root / "manifest.json", {
        "schema": 1,
        "kind": "sources",
        "complete": True,
        "created_at": "2026-09-18T00:00:00Z",
        "documents": [
            {"id": "server", "title": "Server", "path": "docs/fastmcp/server.md",
             "source": "fastmcp", "version": "test", "url": "https://example.test/server"},
            {"id": "tools", "title": "Tools", "path": "docs/mcp/tools.md",
             "source": "mcp", "version": "test", "url": "https://example.test/tools"},
        ],
        "files": {name: digest(root / name) for name in contents},
        "sources": {
            "fastmcp": {"index_url": "https://example.test/fastmcp"},
            "mcp": {"index_url": "https://example.test/mcp"},
        },
    })


def main() -> None:
    """Build and query a real bundle, failing clearly when Ollama is unavailable."""
    os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("OPENAI_API_KEY", "ollama-local")
    os.environ.setdefault("EMBEDDING_MODEL", "bge-m3")
    try:
        embedder = Embedder(timeout=30)
        probe = embedder.encode(["availability test"])
    except Exception as exc:
        raise SystemExit(
            "Ollama/BGE-M3 is unavailable. Run `ollama pull bge-m3` and start Ollama."
        ) from exc
    if probe.shape != (1, 1024):
        raise SystemExit(f"Dimension BGE-M3 inattendue : {probe.shape}")

    with tempfile.TemporaryDirectory(prefix="mcp-builder-ollama-") as directory:
        root = Path(directory)
        sources, indexed = root / "sources", root / "indexed"
        sources.mkdir()
        make_sources(sources)
        build(sources, indexed, embedder=embedder)
        store = Store(indexed, embedder=embedder)
        with TestClient(create_app(store)) as client:
            response = client.get("/health")
            if response.status_code != 200 or response.json() != {"status": "ok"}:
                raise SystemExit(f"Invalid health check: {response.status_code}")
        for mode in ("lexical", "semantic", "hybrid"):
            if not store.search("How do I create an MCP server?", mode=mode):
                raise SystemExit(f"No results in {mode} mode")
    print("Ollama bge-m3: health, lexical, semantic, and hybrid checks passed")


if __name__ == "__main__":
    main()
