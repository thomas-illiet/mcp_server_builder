"""Tests for the OpenAI-compatible embedding client."""

import httpx
import numpy as np
import pytest

from mcp_builder.search.embedding import Embedder


def make_embedder(handler, **kwargs):
    """Create an embedder backed by a deterministic HTTP transport."""
    return Embedder(
        base_url="http://embeddings.test/v1",
        api_key="test-secret",
        model="bge-m3",
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
        **kwargs,
    )


def test_encode_preserves_index_order_normalizes_and_authenticates():
    """Responses may be unordered, but returned rows match input order."""
    def handler(request):
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-secret"
        import json
        assert json.loads(request.read()) == {"model": "bge-m3", "input": ["a", "b"]}
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0, 3]},
            {"index": 0, "embedding": [4, 0]},
        ]})

    result = make_embedder(handler).encode(["a", "b"])
    assert result.dtype == np.float32
    np.testing.assert_allclose(result, [[1, 0], [0, 1]])


def test_retries_transient_statuses_three_times():
    """429 and server failures are retried with a bounded attempt count."""
    statuses = iter([429, 503, 200])
    calls = []

    def handler(request):
        status = next(statuses)
        calls.append(status)
        if status == 200:
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1]}]})
        return httpx.Response(status)

    np.testing.assert_allclose(make_embedder(handler).encode(["a"]), [[1]])
    assert calls == [429, 503, 200]


@pytest.mark.parametrize("payload", [
    {},
    {"data": []},
    {"data": [{"index": 1, "embedding": [1]}]},
    {"data": [{"index": 0, "embedding": [0]}]},
    {"data": [{"index": 0, "embedding": [float("nan")]}]},
])
def test_rejects_invalid_responses(payload):
    """Malformed, missing, non-finite and zero vectors are rejected."""
    embedder = make_embedder(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(ValueError):
        embedder.encode(["a"])


def test_transport_failure_is_bounded():
    """Transport errors never trigger an unbounded retry loop."""
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(RuntimeError, match="unavailable"):
        make_embedder(handler).encode(["a"])
    assert calls == 3


def test_requires_v1_url_and_secret(tmp_path):
    """Configuration fails locally without a standard base URL or credential."""
    with pytest.raises(ValueError, match="end with /v1"):
        Embedder(base_url="http://example.test", api_key="key")
    with pytest.raises(ValueError, match="OPENAI_API_KEY_FILE"):
        Embedder(base_url="http://example.test/v1", api_key_file=tmp_path / "missing")
