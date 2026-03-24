import asyncio
from functools import lru_cache
from typing import Union

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Singleton model loader ────────────────────────────────────────────────────
# Model is downloaded once (~80MB for all-MiniLM-L6-v2) and cached in memory.
# lru_cache ensures we never load it twice even under concurrent startup.

@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    """
    Loads the sentence-transformer model from HuggingFace Hub (first run)
    or local cache (~/.cache/huggingface) on subsequent runs.

    Default: all-MiniLM-L6-v2
      - 384-dimensional embeddings
      - ~80MB model size
      - Runs on CPU — no GPU required
      - ~500 sentences/sec on a modern laptop CPU

    To upgrade to a larger model (better quality, more RAM):
      Set EMBEDDING_MODEL=all-mpnet-base-v2 (768-dim, ~420MB)
      Also update EMBEDDING_DIMENSION=768 and the vector column in migrations.
    """
    logger.info("loading_embedding_model", model=get_settings().EMBEDDING_MODEL)
    model = SentenceTransformer(get_settings().EMBEDDING_MODEL)
    logger.info("embedding_model_loaded", model=get_settings().EMBEDDING_MODEL)
    return model


class EmbeddingService:
    """
    Wraps SentenceTransformer to provide async-safe embedding generation.

    SentenceTransformer.encode() is CPU-bound and synchronous.
    We run it in a thread pool via asyncio.to_thread() so it never
    blocks the FastAPI event loop.
    """

    def __init__(self):
        # Load model eagerly at service creation time
        self._model = _load_model()
        self._dimension = get_settings().EMBEDDING_DIMENSION
        self._batch_size = get_settings().EMBEDDING_BATCH_SIZE

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        """
        Embeds a single string.
        Returns a list[float] of length EMBEDDING_DIMENSION.
        """
        vector = await asyncio.to_thread(
            self._model.encode,
            text,
            normalize_embeddings=True,   # cosine similarity works on unit vectors
            show_progress_bar=False,
        )
        return vector.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of strings in one batched call.
        Much faster than calling embed_text() in a loop.
        Returns list of vectors in the same order as input.
        """
        if not texts:
            return []

        vectors = await asyncio.to_thread(
            self._model.encode,
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.tolist()

    def cosine_similarity(
        self,
        vec_a: list[float],
        vec_b: list[float],
    ) -> float:
        """
        Computes cosine similarity between two vectors.
        Used by the critic agent to compare claim embeddings against chunks.
        Returns a float in [0.0, 1.0] (vectors are already L2-normalized).
        """
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        # Since vectors are normalized, dot product == cosine similarity
        return float(np.dot(a, b))


# ── FastAPI dependency ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """
    Cached singleton dependency for use across the app.

    Usage in services:
        embedder = get_embedding_service()
        vector = await embedder.embed_text("What is RAG?")
    """
    return EmbeddingService()
