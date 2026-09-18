"""Immutable, verified documentation bundles and hybrid retrieval."""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from mcp_builder import BUILDER_VERSION, DEFAULT_EMBEDDING_MODEL, SCHEMA_VERSION
from mcp_builder.corpus.files import digest, resolve_bundle, safe_path
from mcp_builder.search.embedding import EmbeddingUnavailableError


def verify_bundle(root: Path, model_id: str | None = None) -> dict:
    """Return the manifest after checking model identity, hashes and index coherence.

    SQLite must have contiguous passage IDs and pass its integrity check.
    The NumPy rows must match those IDs and contain finite unit vectors.
    Invalid bundles raise ValueError; files are inspected in read-only mode.
    """
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not manifest.get("complete"):
        raise ValueError("Lot incomplet ou format non supporté")
    expected_model = model_id or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    if manifest.get("model") != {"provider": "openai-compatible", "id": expected_model}:
        raise ValueError("Modèle du lot incompatible ; reconstruire les index")
    for name, expected in manifest["files"].items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Échec d'intégrité : {name}")
    required = {"index.sqlite", "vectors.npy"}
    required.update(doc["path"] for doc in manifest["documents"])
    if not required.issubset(manifest["files"]):
        raise ValueError("Fichiers requis absents du manifeste")
    db = sqlite3.connect((root / "index.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    try:
        total, first, last = db.execute("SELECT count(*),min(id),max(id) FROM passages").fetchone()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Index SQLite invalide")
        if total < 1 or first != 0 or last != total - 1:
            raise ValueError("Identifiants de passages incohérents")
    finally:
        db.close()
    vectors = np.load(root / "vectors.npy", mmap_mode="r", allow_pickle=False)
    try:
        if vectors.shape != (total, manifest["dimensions"]) or total != manifest["passages"]:
            raise ValueError("Index et vecteurs incohérents")
        if not np.isfinite(vectors).all() or not np.allclose(
            np.linalg.norm(vectors, axis=1), 1, atol=1e-4
        ):
            raise ValueError("Vecteurs non normalisés ou invalides")
    finally:
        del vectors
    return manifest


def build_index(root: Path, documents: list[dict], embedder) -> int:
    """Write FTS5 passages and normalized vectors, returning the passage count.

    The caller provides an empty output area and a compatible embedder.
    Passage IDs are zero-based vector row numbers; FTS row IDs match them.
    Embedding batches are bounded at 128 passages. Failed output is not a
    publishable bundle and must be discarded by the caller or Docker build.
    """
    from .chunking import chunks

    db = sqlite3.connect(root / "index.sqlite")
    try:
        db.executescript("""
            CREATE TABLE passages (
                id INTEGER PRIMARY KEY, doc_id TEXT, title TEXT, section TEXT,
                content TEXT, source TEXT, version TEXT, url TEXT
            );
            CREATE VIRTUAL TABLE search USING fts5(title, section, content,
                tokenize='unicode61 remove_diacritics 2');
        """)
        texts = []
        for doc in documents:
            raw = (root / doc["path"]).read_text(encoding="utf-8")
            for section, content in chunks(raw):
                index = len(texts)
                db.execute("INSERT INTO passages VALUES (?,?,?,?,?,?,?,?)", (
                    index, doc["id"], doc["title"], section, content,
                    doc["source"], doc["version"], doc["url"],
                ))
                db.execute("INSERT INTO search(rowid,title,section,content) VALUES (?,?,?,?)",
                           (index, doc["title"], section, content))
                texts.append(content)
        if not texts:
            raise ValueError("Aucun passage documentaire")
        # Bounded batches avoid keeping an additional corpus-sized embedding input in RAM.
        first_end = min(128, len(texts))
        first_batch = embedder.encode(texts[:first_end])
        vectors = np.lib.format.open_memmap(
            root / "vectors.npy", mode="w+", dtype=np.float32,
            shape=(len(texts), first_batch.shape[1]),
        )
        print(f"Indexation : {len(texts)} passages", flush=True)
        vectors[:first_end] = first_batch
        print(f"Embeddings : {first_end}/{len(texts)}", flush=True)
        for start in range(first_end, len(texts), 128):
            vectors[start:start + 128] = embedder.encode(texts[start:start + 128])
            print(f"Embeddings : {min(start + 128, len(texts))}/{len(texts)}", flush=True)
        vectors.flush()
        del vectors
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Index SQLite invalide")
        return len(texts)
    finally:
        db.close()


class Store:
    """Read a verified immutable corpus and rank its passages locally.

    Vectors are memory-mapped read-only. Each operation opens its own SQLite
    connection so HTTP worker threads do not share a mutable connection.
    """
    def __init__(self, root: Path, embedder=None, *, concurrency: int = 1):
        """Verify root and load its vectors and configured remote embedder.

        An injected embedder supports deterministic tests without network calls.
        """
        self.root = resolve_bundle(root)
        if embedder is None:
            from .embedding import Embedder
            embedder = Embedder(concurrency=concurrency)
        model_id = getattr(embedder, "model", None)
        self.manifest = verify_bundle(self.root, model_id=model_id)
        self.vectors = np.load(self.root / "vectors.npy", mmap_mode="r", allow_pickle=False)
        self.embedder = embedder

    @contextmanager
    def connect(self):
        """Yield a read-only SQLite connection with named columns and always close it."""
        db = sqlite3.connect((self.root / "index.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def search(self, query: str, k: int = 5, source: str | None = None,
               version: str | None = None, mode: str = "hybrid") -> dict:
        """Return up to k distinct documents ranked by lexical, semantic or hybrid search.

        Source/version filters constrain both candidate sets before ranking.
        Hybrid mode fuses the first 100 results of each ranker with RRF(k=60);
        ties are ordered by passage ID. Each result includes a 1600-character
        snippet and official reference. Invalid inputs raise ValueError; valid
        filters with no matching passages return an envelope containing an empty result list.
        """
        if not query.strip() or len(query.encode("utf-8")) > 7800 or not 1 <= k <= 20:
            raise ValueError("Question vide/trop longue ou k hors de [1,20]")
        if mode not in {"hybrid", "lexical", "semantic"}:
            raise ValueError("Mode inconnu")
        if source not in {None, "fastmcp", "mcp"}:
            raise ValueError("Source inconnue")
        clauses, params = [], []
        if source:
            clauses.append("source=?")
            params.append(source)
        if version:
            clauses.append("version=?")
            params.append(version)
        where = " AND ".join(clauses) or "1=1"
        with self.connect() as db:
            rows = {row["id"]: dict(row) for row in db.execute(
                f"SELECT * FROM passages WHERE {where}", params
            )}
            if not rows:
                return self._search_response([], mode, mode)
            rankings = []
            if mode != "semantic":
                terms = re.findall(r"\w+", query, flags=re.UNICODE)[:64]
                expression = " OR ".join('"' + term + '"' for term in terms)
                lexical = []
                if expression:
                    lexical = [row[0] for row in db.execute(
                        f"""SELECT search.rowid FROM search JOIN passages p ON p.id=search.rowid
                        WHERE search MATCH ? AND {where}
                        ORDER BY bm25(search,5,3,1),search.rowid LIMIT 100""",
                        [expression, *params],
                    )]
                rankings.append(lexical)
            if mode != "lexical":
                try:
                    vector = self.embedder.encode([query], query=True)[0]
                except EmbeddingUnavailableError:
                    if mode == "semantic":
                        raise
                    return self._rank_results(rows, rankings, k, mode, "lexical")
                if vector.shape != (self.manifest["dimensions"],):
                    raise ValueError("Dimension d'embedding incompatible avec l'index")
                ids = np.array(sorted(rows), dtype=np.int64)
                scores = self.vectors[ids] @ vector
                rankings.append(ids[np.argsort(-scores, kind="stable")[:100]].tolist())
        return self._rank_results(rows, rankings, k, mode, mode)

    @staticmethod
    def _search_response(results: list[dict], requested: str, effective: str) -> dict:
        """Wrap results with transparent retrieval mode and fallback metadata."""
        fallback = requested != effective
        warnings = (["Recherche sémantique indisponible ; résultats lexicaux retournés."]
                    if fallback else [])
        return {"results": results, "requested_mode": requested, "effective_mode": effective,
                "fallback_used": fallback, "warnings": warnings}

    def _rank_results(self, rows: dict, rankings: list[list[int]], k: int,
                      requested: str, effective: str) -> dict:
        """Fuse rankings and return one passage per document in a typed envelope."""
        fused = {}
        for ranking in rankings:
            for rank, passage_id in enumerate(ranking, 1):
                fused[passage_id] = fused.get(passage_id, 0.0) + 1.0 / (60 + rank)
        results = []
        # Multiple sections of a page are useful, but one page must not consume all top-k slots.
        seen = set()
        for passage_id in sorted(fused, key=lambda i: (-fused[i], i)):
            row = rows[passage_id]
            if row["doc_id"] in seen:
                continue
            seen.add(row["doc_id"])
            content = row.pop("content")
            row.update(score=fused[passage_id], snippet=content[:1600])
            results.append(row)
            if len(results) == k:
                break
        return self._search_response(results, requested, effective)

    def read(self, doc_id: str, section: str | None = None, offset: int = 0,
             limit: int = 12000) -> dict:
        """Read a page or exact heading with character-based pagination.

        Repeated headings are joined. Return content, total_chars and next_offset
        (None at the end), plus document metadata. Missing pages/sections and
        invalid pagination raise ValueError. This never reconstructs text from vectors.
        """
        if offset < 0 or not 1 <= limit <= 24000:
            raise ValueError("Pagination invalide")
        doc = next((d for d in self.manifest["documents"] if d["id"] == doc_id), None)
        if not doc:
            raise ValueError("Document absent du lot local")
        content = safe_path(self.root, doc["path"]).read_text(encoding="utf-8")
        if section:
            from .chunking import sections
            matches = [text for heading, text in sections(content) if heading == section]
            if not matches:
                raise ValueError("Section absente")
            content = "\n".join(matches)
        end = min(offset + limit, len(content))
        return {**doc, "section": section, "content": content[offset:end],
                "total_chars": len(content), "next_offset": end if end < len(content) else None}

    def status(self) -> dict:
        """Return corpus/model metadata and the integrity status checked at startup."""
        m = self.manifest
        semantic = {
            "configured": True,
            "provider": m["model"]["provider"],
            "model": m["model"]["id"],
            "endpoint": getattr(self.embedder, "base_url", None),
            "timeout_seconds": getattr(self.embedder, "timeout", None),
            "network_checked": False,
        }
        return {key: m[key] for key in (
            "created_at", "model", "fastmcp_tested", "passages", "dimensions", "sources"
        )} | {"schema_version": SCHEMA_VERSION, "server_version": BUILDER_VERSION,
             "documents": len(m["documents"]), "integrity": "verified_at_startup",
             "search": {"lexical": {"available": True, "network_required": False},
                        "semantic": semantic}}
