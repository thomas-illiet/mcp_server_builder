"""Contract checks for every versioned documentation page."""

import json
from pathlib import Path

from mcp_builder.search.store import Store


def test_every_manifest_document_is_addressable_and_readable():
    """Every public doc_id fits the MCP schema and resolves to readable content."""
    root = Path(__file__).parents[1] / "documentation"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    store = Store.__new__(Store)
    store.root = root
    store.manifest = manifest

    assert manifest["documents"]
    for document in manifest["documents"]:
        assert 1 <= len(document["id"]) <= 512
        result = store.read(document["id"], limit=1)
        assert result["id"] == document["id"]
        assert result["total_chars"] >= 1
