from prometheus_client import Counter, Histogram, Gauge, Summary
from app.core.config import get_settings


# ── Request metrics (auto-instrumented by prometheus_fastapi_instrumentator)
# We define custom metrics below for RAG-specific observability.

# ── LLM metrics ───────────────────────────────────────────────────────────────

LLM_REQUEST_COUNT = Counter(
    name="ragops_llm_requests_total",
    documentation="Total number of LLM inference calls.",
    labelnames=["provider", "model", "status"],   # status: success | error
)

LLM_LATENCY = Histogram(
    name="ragops_llm_latency_seconds",
    documentation="LLM response latency in seconds (first token to last).",
    labelnames=["provider", "model"],
    # Buckets tuned for local quantized models (slow) vs. API (fast)
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

LLM_TOKEN_COUNT = Counter(
    name="ragops_llm_tokens_total",
    documentation="Total tokens consumed by LLM calls.",
    labelnames=["provider", "model", "direction"],  # direction: prompt | completion
)

# ── Retrieval metrics ─────────────────────────────────────────────────────────

RETRIEVAL_LATENCY = Histogram(
    name="ragops_retrieval_latency_seconds",
    documentation="Vector search latency in seconds.",
    labelnames=["backend"],     # pgvector | faiss
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

RETRIEVAL_CHUNK_COUNT = Histogram(
    name="ragops_retrieval_chunks_returned",
    documentation="Number of chunks returned per retrieval call.",
    labelnames=["backend"],
    buckets=[1, 2, 3, 5, 8, 10, 15, 20],
)

# ── Critic metrics ────────────────────────────────────────────────────────────

CRITIC_SCORE = Histogram(
    name="ragops_critic_score",
    documentation="Distribution of critic confidence scores (0.0–1.0).",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

CRITIC_VERIFIED_CLAIMS = Counter(
    name="ragops_critic_verified_claims_total",
    documentation="Total claims verified by the critic agent.",
    labelnames=["status"],      # verified | unverified | partial
)

# ── Ingestion metrics ─────────────────────────────────────────────────────────

INGESTION_COUNT = Counter(
    name="ragops_ingestion_total",
    documentation="Total documents ingested.",
    labelnames=["status"],      # success | failed
)

INGESTION_CHUNK_COUNT = Counter(
    name="ragops_ingestion_chunks_total",
    documentation="Total chunks created during ingestion.",
)

INGESTION_LATENCY = Histogram(
    name="ragops_ingestion_latency_seconds",
    documentation="Time to fully ingest a document (parse + embed + store).",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# ── Active sessions gauge ─────────────────────────────────────────────────────

ACTIVE_QUERIES = Gauge(
    name="ragops_active_queries",
    documentation="Number of query requests currently being processed.",
)

# ── Helper context managers ───────────────────────────────────────────────────

class track_llm_call:
    """
    Context manager to track LLM call latency and status.

    Usage:
        async with track_llm_call(provider="local", model="llama-3.2-3b"):
            response = await llm_client.generate(prompt)
    """
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        self._timer = None

    def __enter__(self):
        self._timer = LLM_LATENCY.labels(
            provider=self.provider, model=self.model
        ).time()
        self._timer.__enter__()
        ACTIVE_QUERIES.inc()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._timer.__exit__(exc_type, exc_val, exc_tb)
        ACTIVE_QUERIES.dec()
        status = "error" if exc_type else "success"
        LLM_REQUEST_COUNT.labels(
            provider=self.provider, model=self.model, status=status
        ).inc()


class track_retrieval:
    """
    Context manager to track vector search latency.

    Usage:
        async with track_retrieval(backend="pgvector") as t:
            chunks = await vector_store.search(query_embedding, top_k=5)
            t.set_chunk_count(len(chunks))
    """
    def __init__(self, backend: str):
        self.backend = backend
        self._timer = None
        self._chunk_count = 0

    def set_chunk_count(self, n: int):
        self._chunk_count = n

    def __enter__(self):
        self._timer = RETRIEVAL_LATENCY.labels(backend=self.backend).time()
        self._timer.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._timer.__exit__(exc_type, exc_val, exc_tb)
        if not exc_type:
            RETRIEVAL_CHUNK_COUNT.labels(backend=self.backend).observe(
                self._chunk_count
            )
