"""The runtime never resolves a model name over the network."""

import os
from pathlib import Path
from threading import BoundedSemaphore

import numpy as np


class Embedder:
    """Encode E5 queries and passages on CPU using only local model files.

    Vectors are normalized float32 arrays. A semaphore bounds simultaneous
    model calls; no model resolution or remote code execution is allowed.
    """
    def __init__(self, model_path: Path, concurrency: int = 1, threads: int = 2):
        """Load model_path locally and configure CPU threads and concurrency.

        The directory must contain a complete SentenceTransformer model.
        Missing files or invalid runtime settings fail during initialization.
        """
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        import torch
        from sentence_transformers import SentenceTransformer

        if not model_path.is_dir():
            raise ValueError(f"Modèle local absent : {model_path}")
        torch.set_num_threads(threads)
        self.model = SentenceTransformer(
            str(model_path.resolve()), device="cpu", local_files_only=True,
            trust_remote_code=False,
        )
        self.model.max_seq_length = 512
        self.tokenizer = self.model.tokenizer
        self.gate = BoundedSemaphore(concurrency)

    def token_count(self, text: str) -> int:
        """Count tokenizer tokens, including special tokens, without encoding a vector."""
        return len(self.tokenizer.encode(text, add_special_tokens=True))

    def encode(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        """Return an (N, dimensions) array of unit vectors for the supplied texts.

        query selects the E5 query prefix; passages use the passage prefix.
        Raise ValueError when a prefixed input exceeds the 512-token limit
        instead of silently truncating it. Model calls share the semaphore.
        """
        prefix = "query: " if query else "passage: "
        values = [prefix + text for text in texts]
        if any(self.token_count(text) > 512 for text in values):
            raise ValueError("Texte trop long pour le modèle (512 tokens maximum).")
        with self.gate:
            return np.asarray(self.model.encode(
                values, batch_size=32, normalize_embeddings=True,
                convert_to_numpy=True, show_progress_bar=False,
            ), dtype=np.float32)
