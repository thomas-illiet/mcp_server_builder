"""Filesystem helpers for verified local documentation and search bundles."""
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    """Return a file's SHA-256 hex digest, reading in bounded 1 MiB blocks."""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a relative bundle path and reject the root itself or any escape.

    Resolution includes symlinks; invalid paths raise ValueError. The target
    need not exist yet, so this helper also supports safe output paths.
    """
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Chemin en dehors du lot")
    return path


def resolve_bundle(root: Path) -> Path:
    """Require a manifest directory, with synchronization guidance when absent."""
    if (root / "manifest.json").exists():
        return root
    raise ValueError("Sources missing: run bash scripts/sync-docs.sh")


def write_json(path: Path, value):
    """Write readable UTF-8 JSON with LF endings; atomic replacement is the caller's job."""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def readable_tree(root: Path):
    """Publication permissions must work for the runtime's non-root UID."""
    root.chmod(0o755)
    for path in root.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
