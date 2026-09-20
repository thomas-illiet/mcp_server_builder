"""Bundle and retrieval tests with deterministic embeddings."""

import httpx
import numpy as np
import pytest

from mcp_builder.corpus.files import digest, write_json
from mcp_builder.search.embedding import Embedder, EmbeddingUnavailableError
from mcp_builder.search.index import build
from mcp_builder.search.store import Store, verify_bundle


class FakeEmbedder:
    """Return two-dimensional vectors without external calls."""

    model = "bge-m3"

    def encode(self, texts, *, query=False):
        """Map banana text and all other text to orthogonal vectors."""
        del query
        return np.asarray(
            [[1.0, 0.0] if "banana" in text.lower() else [0.0, 1.0] for text in texts],
            dtype=np.float32,
        )


class OfflineEmbedder(FakeEmbedder):
    """Fail if a lexical-only search attempts a remote embedding."""

    def encode(self, texts, *, query=False):
        """Reject every unexpected embedding call."""
        raise AssertionError("lexical search contacted the embedder")


def source_bundle(root):
    """Create the smallest valid source bundle accepted by the indexer."""
    (root / "docs/fastmcp").mkdir(parents=True)
    (root / "docs/mcp").mkdir(parents=True)
    (root / "indexes").mkdir()
    files = {
        "docs/fastmcp/banana.md": "# Banana\nBanana retrieval documentation.\n",
        "docs/mcp/apple.md": "# Apple\nApple protocol documentation.\n",
        "indexes/fastmcp.txt": "fastmcp\n",
        "indexes/mcp.txt": "mcp\n",
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    documents = [
        {"id": "banana", "title": "Banana", "path": "docs/fastmcp/banana.md",
         "source": "fastmcp", "version": "test", "url": "https://example.test/banana"},
        {"id": "apple", "title": "Apple", "path": "docs/mcp/apple.md",
         "source": "mcp", "version": "test", "url": "https://example.test/apple"},
    ]
    write_json(root / "manifest.json", {
        "schema": 1,
        "kind": "sources",
        "complete": True,
        "created_at": "2026-09-18T00:00:00Z",
        "documents": documents,
        "files": {name: digest(root / name) for name in files},
        "sources": {
            "fastmcp": {"index_url": "https://example.test/fastmcp"},
            "mcp": {"index_url": "https://example.test/mcp"},
        },
    })


@pytest.fixture
def indexed_bundle(tmp_path):
    """Build a valid bundle around a fake BGE-compatible embedder."""
    sources = tmp_path / "sources"
    output = tmp_path / "indexed"
    sources.mkdir()
    source_bundle(sources)
    build(sources, output, embedder=FakeEmbedder())
    return output


@pytest.fixture
def lexical_bundle(tmp_path):
    """Build a complete FTS5 bundle without endpoint configuration or vectors."""
    sources = tmp_path / "sources"
    output = tmp_path / "indexed"
    sources.mkdir()
    source_bundle(sources)
    build(sources, output, semantic=False)
    return output


def test_manifest_records_remote_model_and_rejects_e5(indexed_bundle):
    """Only the exact OpenAI-compatible model contract is accepted."""
    manifest = verify_bundle(indexed_bundle, model_id="bge-m3")
    assert manifest["model"] == {"provider": "openai-compatible", "id": "bge-m3"}
    manifest["model"] = {"id": "intfloat/multilingual-e5-small", "revision": "old"}
    write_json(indexed_bundle / "manifest.json", manifest)
    with pytest.raises(ValueError, match="model mismatch"):
        verify_bundle(indexed_bundle, model_id="bge-m3")


def test_lexical_search_never_calls_embedder(indexed_bundle):
    """Lexical retrieval remains available without the remote endpoint."""
    store = Store(indexed_bundle, embedder=OfflineEmbedder())
    response = store.search("banana", mode="lexical")
    assert response["results"][0]["doc_id"] == "banana"
    assert response["fallback_used"] is False


def test_lexical_only_bundle_starts_without_embedding_configuration(lexical_bundle):
    """The default local bundle needs neither endpoint, secret, model, nor vectors."""
    store = Store(lexical_bundle)
    manifest = verify_bundle(lexical_bundle)
    assert manifest["search"] == {"lexical": True, "semantic": False}
    assert manifest["model"] is None
    assert not (lexical_bundle / "vectors.npy").exists()
    response = store.search("banana", mode="hybrid")
    assert response["results"][0]["doc_id"] == "banana"
    assert response["effective_mode"] == "lexical"
    assert response["fallback_used"] is True
    status = store.status()
    assert status["status"] == "ok"
    assert status["search"]["semantic"]["state"] == "disabled"


def test_lexical_only_bundle_rejects_semantic_mode(lexical_bundle):
    """A semantic-only request fails clearly instead of pretending it ran."""
    store = Store(lexical_bundle)
    with pytest.raises(EmbeddingUnavailableError, match="not configured"):
        store.search("banana", mode="semantic")


def test_hybrid_falls_back_only_for_endpoint_unavailability(indexed_bundle):
    """Hybrid retrieval returns lexical results and advertises its degraded mode."""
    class UnavailableEmbedder(FakeEmbedder):
        def encode(self, texts, *, query=False):
            raise EmbeddingUnavailableError("offline")

    store = Store(indexed_bundle, embedder=UnavailableEmbedder())
    response = store.search("banana", mode="hybrid")
    assert response["results"][0]["doc_id"] == "banana"
    assert response["requested_mode"] == "hybrid"
    assert response["effective_mode"] == "lexical"
    assert response["fallback_used"] is True
    assert response["warnings"]


@pytest.mark.parametrize("failure", ["network", "timeout", "429", "503"])
def test_hybrid_falls_back_for_transient_http_failures(indexed_bundle, failure):
    """Network, timeout, rate limit and server errors all preserve lexical search."""
    def handler(request):
        if failure == "network":
            raise httpx.ConnectError("offline", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("late", request=request)
        return httpx.Response(int(failure))

    embedder = Embedder(
        base_url="http://embeddings.test/v1", api_key="secret", model="bge-m3",
        transport=httpx.MockTransport(handler), sleeper=lambda _: None,
    )
    response = Store(indexed_bundle, embedder=embedder).search("banana", mode="hybrid")
    assert response["effective_mode"] == "lexical"
    assert response["fallback_used"] is True


def test_search_filters_and_empty_results_use_the_envelope(indexed_bundle):
    """Filters constrain results and no-match searches retain response metadata."""
    store = Store(indexed_bundle, embedder=FakeEmbedder())
    assert store.search("banana", source="mcp", mode="lexical")["results"] == []
    assert store.search("banana", version="missing", mode="hybrid") == {
        "results": [], "requested_mode": "hybrid", "effective_mode": "hybrid",
        "fallback_used": False, "warnings": [],
    }


def test_status_reports_search_configuration_without_network(indexed_bundle):
    """Status describes both retrieval modes without calling the endpoint."""
    store = Store(indexed_bundle, embedder=OfflineEmbedder())
    status = store.status()
    assert status["search"]["lexical"] == {"available": True, "network_required": False}
    assert status["search"]["semantic"]["network_checked"] is False


def test_semantic_dimension_must_match_bundle(indexed_bundle):
    """A provider returning a changed vector dimension cannot reach matrix math."""
    class WrongDimension(FakeEmbedder):
        def encode(self, texts, *, query=False):
            return np.ones((len(texts), 3), dtype=np.float32)

    store = Store(indexed_bundle, embedder=WrongDimension())
    with pytest.raises(ValueError, match="dimension"):
        store.search("banana", mode="semantic")
