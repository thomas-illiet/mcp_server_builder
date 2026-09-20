"""Build search indexes exclusively from a verified, local source snapshot."""
import argparse
import shutil
from pathlib import Path

import numpy as np

from mcp_builder import FASTMCP_VERSION
from mcp_builder.corpus.files import digest, readable_tree, resolve_bundle, write_json
from mcp_builder.corpus.manifest import verify_sources

from .store import build_index, verify_bundle


def build(sources: Path, output: Path, *, embedder=None, semantic: bool = True):
    """Create and verify an indexed bundle from a local source snapshot.

    Documents are copied into a previously absent output folder. The injected
    embedder is for tests; otherwise the configured OpenAI-compatible endpoint
    is used when semantic indexing is enabled. A lexical-only bundle does not
    need an endpoint, secret, vector file, or model metadata. Return the indexed
    manifest, linked to the source manifest hash. Failures may leave partial
    output but never modify the sources; Docker publishes the layer only after
    this command succeeds.
    """
    root = resolve_bundle(sources)
    source_manifest = verify_sources(root)
    if output.exists():
        raise ValueError("The index output directory must not exist to prevent overwriting")
    shutil.copytree(root, output)
    if semantic and embedder is None:
        from .embedding import Embedder
        embedder = Embedder()
    if not semantic and embedder is not None:
        raise ValueError("A lexical-only build cannot use an embedder")
    total = build_index(output, source_manifest["documents"], embedder)
    dimensions = 0
    if semantic:
        vectors = np.load(output / "vectors.npy", mmap_mode="r")
        dimensions = vectors.shape[1]
        del vectors
    manifest = {**source_manifest, "kind": "indexed", "passages": total,
                "search": {"lexical": True, "semantic": semantic},
                "model": ({"provider": "openai-compatible", "id": embedder.model}
                          if semantic else None),
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
    verify_bundle(output, model_id=embedder.model if semantic else None)
    readable_tree(output)
    return manifest


def main():
    """Parse local source/output paths and build indexes without downloading data."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--lexical-only",
        action="store_true",
        help="Build FTS5 without calling an embedding endpoint",
    )
    args = p.parse_args()
    result = build(args.sources, args.output, semantic=not args.lexical_only)
    mode = "hybrid" if result["search"]["semantic"] else "lexical"
    print(
        f"Index verified: {result['passages']} passages, mode={mode}, "
        f"dimensions={result['dimensions']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
