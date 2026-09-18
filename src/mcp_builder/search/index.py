"""Build search indexes exclusively from a verified, local source snapshot."""
import argparse
import shutil
from pathlib import Path

import numpy as np

from mcp_builder import FASTMCP_VERSION
from mcp_builder.corpus.files import digest, readable_tree, resolve_bundle, write_json
from mcp_builder.corpus.manifest import verify_sources

from .store import build_index, verify_bundle


def build(sources: Path, output: Path, *, embedder=None):
    """Create and verify an indexed bundle from a local source snapshot.

    Documents are copied into a previously absent output folder. The injected
    embedder is for tests; otherwise the configured OpenAI-compatible endpoint
    is used. Return the indexed manifest, linked to the source manifest
    hash. Failures may leave partial output but never modify the sources;
    Docker publishes the layer only after this command succeeds.
    """
    root = resolve_bundle(sources)
    source_manifest = verify_sources(root)
    if output.exists():
        raise ValueError("Le dossier d'indexation doit être absent pour éviter tout écrasement")
    shutil.copytree(root, output)
    if embedder is None:
        from .embedding import Embedder
        embedder = Embedder()
    total = build_index(output, source_manifest["documents"], embedder)
    vectors = np.load(output / "vectors.npy", mmap_mode="r")
    dimensions = vectors.shape[1]
    del vectors
    manifest = {**source_manifest, "kind": "indexed", "passages": total,
                "model": {"provider": "openai-compatible", "id": embedder.model},
                "dimensions": dimensions, "fastmcp_tested": FASTMCP_VERSION,
                "source_manifest_sha256": digest(root / "manifest.json")}
    manifest["sources"] = {
        name: {**metadata, "versions": sorted({doc["version"] for doc in manifest["documents"]
                                               if doc["source"] == name})}
        for name, metadata in manifest["sources"].items()
    }
    manifest["files"] = {p.relative_to(output).as_posix(): digest(p)
                         for p in output.rglob("*") if p.is_file() and p.name != "manifest.json"}
    write_json(output / "manifest.json", manifest)
    verify_bundle(output, model_id=embedder.model)
    readable_tree(output)
    return manifest


def main():
    """Parse local source/output paths and build indexes without downloading data."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = build(args.sources, args.output)
    print(f"Index vérifié : {result['passages']} passages, {result['dimensions']} dimensions", flush=True)


if __name__ == "__main__":
    main()
