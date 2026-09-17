"""Verify source snapshots without downloading or importing compute libraries."""
import json
from pathlib import Path

from mcp_builder import MODEL_ID, MODEL_REVISION

from .files import digest, safe_path


def verify_sources(root: Path):
    """Verify and return a complete source manifest without importing compute libraries.

    Check required source files, exact file inventory and
    SHA-256 hashes. Search indexes are forbidden. This verifies snapshot
    integrity, not the semantic correctness of the upstream documentation.
    """
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if m.get("kind") != "sources" or m.get("schema") != 1 or not m.get("complete"):
        raise ValueError("Source batch is incomplete or incompatible")
    if "model" in m and m["model"] != {"id": MODEL_ID, "revision": MODEL_REVISION}:
        raise ValueError("Incompatible model revision")
    if not m["documents"] or not {"fastmcp", "mcp"}.issubset(m["sources"]):
        raise ValueError("Missing official sources")
    required = {"indexes/fastmcp.txt", "indexes/mcp.txt"}
    required.update(d["path"] for d in m["documents"])
    if not required.issubset(m["files"]):
        raise ValueError("Missing source files")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(m["files"]) | {"manifest.json"}:
        raise ValueError("Extra or missing files in the source batch")
    for name, expected in m["files"].items():
        if name.endswith((".sqlite", ".npy")):
            raise ValueError("A source batch must not contain search indexes")
        if digest(safe_path(root, name)) != expected:
            raise ValueError(f"Integrity check failed: {name}")
    return m
