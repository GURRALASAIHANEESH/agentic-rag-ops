# backend/app/services/embedder.py
import asyncio
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    Unified embedding service supporting two backends:

      1. SentenceTransformer (local) — default, free, runs on CPU
         EMBEDDING_MODEL=all-MiniLM-L6-v2  → 384-dim
         EMBEDDING_MODEL=all-mpnet-base-v2  → 768-dim

      2. OpenAI API — cloud, best quality, minimal cost
         EMBEDDING_MODEL=text-embedding-3-small → 1536-dim
         EMBEDDING_MODEL=text-embedding-3-large → 3072-dim

    Backend is selected automatically based on EMBEDDING_MODEL value.
    No code changes needed — just update .env and re-ingest documents.
    """

    def __init__(self):
        cfg = get_settings()
        self._model_name = cfg.EMBEDDING_MODEL
        self._dimension  = cfg.EMBEDDING_DIMENSION
        self._batch_size = cfg.EMBEDDING_BATCH_SIZE
        self._is_openai  = self._model_name.startswith("text-embedding-")
        self._is_nomic   = "nomic-embed" in self._model_name

        if self._is_openai:
            self._init_openai(cfg)
        elif self._is_nomic:
            self._init_nomic(cfg)
        else:
            self._init_sentence_transformer()

    def _init_nomic(self, cfg) -> None:
        import os
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. Run: pip install sentence-transformers"
            )
        cache_dir = os.environ.get("HF_HOME", None)
        logger.info("loading_embedding_model", model=self._model_name, cache=cache_dir)
        self._model = SentenceTransformer(
            "nomic-ai/nomic-embed-text-v1.5",
            trust_remote_code=True,
            cache_folder=cache_dir,
            revision="e5cf08aadaa33385f5990def41f7a23405aec398",
        )
        self._is_nomic = False
        logger.info("embedding_backend_nomic_st", model=self._model_name)

    def _init_openai(self, cfg) -> None:
        """Initializes the OpenAI async client."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            )
        api_key = getattr(cfg, "OPENAI_API_KEY", None)
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set in .env but EMBEDDING_MODEL is an OpenAI model."
            )
        self._client = AsyncOpenAI(api_key=api_key)
        logger.info("embedding_backend_openai", model=self._model_name)

    def _init_sentence_transformer(self) -> None:
        """Loads SentenceTransformer model into memory (cached after first load)."""
        from sentence_transformers import SentenceTransformer
        logger.info("loading_embedding_model", model=self._model_name)
        self._model = SentenceTransformer(self._model_name)
        logger.info("embedding_model_loaded", model=self._model_name)

    @property
    def dimension(self) -> int:
        return self._dimension

    # ── Public API ────────────────────────────────────────────────────────────

    async def embed_text(self, text: str) -> list[float]:
        """Embeds a single string. Returns list[float] of length EMBEDDING_DIMENSION."""
        if self._is_openai:
            return await self._openai_embed_single(text)
        elif self._is_nomic:
            return await self._nomic_embed_single(text)
        return await self._local_embed_text(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds a list of strings. Returns list of vectors in same order as input."""
        if not texts:
            return []
        if self._is_openai:
            return await self._openai_embed(texts)
        elif self._is_nomic:
            return await self._nomic_embed_batch(texts)
        return await self._local_embed_batch(texts)

    def cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """
        Cosine similarity between two L2-normalized vectors.
        Used by the critic agent. Returns float in [0.0, 1.0].
        """
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        return float(np.dot(a, b))

    # ── OpenAI backend ────────────────────────────────────────────────────────

    async def _openai_embed_single(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model_name,
            input=text,
            encoding_format="float",
        )
        return response.data[0].embedding

    async def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        """
        Batches OpenAI embedding calls in groups of 100.
        OpenAI supports up to 2048 inputs per request but 100 is safe
        and keeps individual request latency low.
        """
        all_vectors: list[list[float]] = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await self._client.embeddings.create(
                model=self._model_name,
                input=batch,
                encoding_format="float",
            )
            # OpenAI returns results sorted by index — safe to extend in order
            all_vectors.extend([item.embedding for item in response.data])
            logger.info(
                "openai_embed_batch",
                batch=i // batch_size + 1,
                texts=len(batch),
                total_so_far=len(all_vectors),
            )

        return all_vectors

    # ── Nomic backend ─────────────────────────────────────────────────────────

    async def _nomic_embed_single(self, text: str) -> list[float]:
        result = await asyncio.to_thread(
            self._nomic_embed.text,
            texts=[text],
            model=self._model_name,
            task_type="search_query",
            dimensionality=self._dimension,
        )
        return result["embeddings"][0]

    async def _nomic_embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = await asyncio.to_thread(
            self._nomic_embed.text,
            texts=texts,
            model=self._model_name,
            task_type="search_document",
            dimensionality=self._dimension,
        )
        return result["embeddings"]

    # ── Local SentenceTransformer backend ─────────────────────────────────────

    async def _local_embed_text(self, text: str) -> list[float]:
        vector = await asyncio.to_thread(
            self._model.encode,
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()

    async def _local_embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = await asyncio.to_thread(
            self._model.encode,
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.tolist()


# ── FastAPI dependency ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Cached singleton. Import and call this everywhere embeddings are needed."""
    return EmbeddingService()
