"""OpenAI-compatible dense embeddings without local model files."""

import os
import time
from pathlib import Path
from threading import BoundedSemaphore
from typing import Callable
from urllib.parse import urlsplit

import httpx
import numpy as np

from mcp_builder import DEFAULT_EMBEDDING_MODEL


class EmbeddingUnavailableError(RuntimeError):
    """Report a transient failure of the configured embedding endpoint."""


def _secret(value: str | None, file_name: str | None) -> str:
    """Resolve a direct secret or a secret file without exposing its value."""
    if value:
        return value
    if file_name:
        try:
            result = Path(file_name).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("Cannot read OPENAI_API_KEY_FILE") from exc
        if result:
            return result
    raise ValueError("OPENAI_API_KEY or OPENAI_API_KEY_FILE is required")


class Embedder:
    """Encode text through an OpenAI-compatible ``/v1/embeddings`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_file: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        concurrency: int = 1,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        """Load configuration locally; endpoint availability is checked only on encode."""
        base_url = (base_url or os.getenv("OPENAI_BASE_URL", "")).rstrip("/")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.path.endswith("/v1")
        ):
            raise ValueError(
                "OPENAI_BASE_URL must be an HTTP(S) /v1 URL without credentials"
            )
        self.model = model or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        if not self.model.strip():
            raise ValueError("EMBEDDING_MODEL cannot be empty")
        key = _secret(
            api_key or os.getenv("OPENAI_API_KEY"),
            api_key_file or os.getenv("OPENAI_API_KEY_FILE"),
        )
        request_timeout = timeout or float(os.getenv("EMBEDDING_TIMEOUT", "60"))
        if request_timeout <= 0 or concurrency < 1:
            raise ValueError("Invalid embedding configuration")
        self.client = client or httpx.Client(
            base_url=base_url + "/",
            headers={"Authorization": f"Bearer {key}"},
            timeout=request_timeout,
            transport=transport,
        )
        self.gate = BoundedSemaphore(concurrency)
        self.sleeper = sleeper
        self.base_url = base_url
        self.timeout = request_timeout

    def encode(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        """Return normalized float32 vectors in the same order as ``texts``.

        BGE-M3 uses raw queries and passages, so ``query`` deliberately adds no prefix.
        Transient endpoint failures are attempted at most three times.
        """
        del query
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("The embedding text list is invalid")
        response = None
        with self.gate:
            for attempt in range(3):
                try:
                    response = self.client.post(
                        "embeddings", json={"model": self.model, "input": texts}
                    )
                except httpx.TransportError as exc:
                    if attempt == 2:
                        raise EmbeddingUnavailableError(
                            "Embedding endpoint unavailable"
                        ) from exc
                else:
                    if response.status_code != 429 and response.status_code < 500:
                        break
                    if attempt == 2:
                        raise EmbeddingUnavailableError(
                            f"Embedding endpoint unavailable (HTTP {response.status_code})"
                        )
                self.sleeper(0.25 * (2**attempt))
        if response is None or response.is_error:
            status = response.status_code if response is not None else "unknown"
            raise RuntimeError(f"Embedding request rejected (HTTP {status})")
        try:
            payload = response.json()
            data = payload["data"]
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError
            ordered = sorted(data, key=lambda item: item["index"])
            if [item["index"] for item in ordered] != list(range(len(texts))):
                raise ValueError
            vectors = np.asarray([item["embedding"] for item in ordered], dtype=np.float32)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid embedding response") from exc
        if vectors.ndim != 2 or vectors.shape[1] < 1 or not np.isfinite(vectors).all():
            raise ValueError("Invalid embedding vectors")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0) or not np.isfinite(norms).all():
            raise ValueError("Zero or invalid embedding vectors")
        return np.asarray(vectors / norms, dtype=np.float32)
