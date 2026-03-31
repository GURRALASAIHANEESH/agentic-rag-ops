# backend/app/core/config.py
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """
    All configuration loaded from environment variables / .env file.

    Never hardcode secrets here — use .env (dev) or GitHub Actions secrets (CI/CD).

    Pydantic-settings reads fields in this priority order:
      1. Environment variables (highest)
      2. .env file
      3. Field default values (lowest)
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),  # parents[2] = backend/
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────
    APP_NAME: str = "Agentic RAG Ops"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # ── Server ────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1  # Increase to CPU count in production

    # ── Database (Postgres + pgvector) ────────────────────────────────────
    DATABASE_URL: str  # e.g. postgresql+asyncpg://user:pass@localhost:5432/ragops
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── JWT Auth ──────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str  # Min 32 chars — generate with: openssl rand -hex 32
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── LLM Provider ──────────────────────────────────────────────────────
    # "local"  → llama.cpp server (run via llm/run_server.sh)
    # "openai" → OpenAI API
    # "groq"   → Groq API (free tier, recommended for dev)
    LLM_PROVIDER: Literal["local", "openai", "groq"] = "groq"

    # Local llama.cpp
    LLAMA_SERVER_URL: str = "http://localhost:8080"
    LLAMA_MODEL_NAME: str = "llama-3.2-3b-q4"
    LLAMA_MAX_TOKENS: int = 1024
    LLAMA_TEMPERATURE: float = 0.1  # Low temp = deterministic = better for RAG

    # OpenAI (only needed if LLM_PROVIDER=openai)
    OPENAI_API_KEY: str = ""
    NOMIC_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Groq (only needed if LLM_PROVIDER=groq)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Embeddings ────────────────────────────────────────────────────────
    # all-MiniLM-L6-v2: 384-dim, ~80MB, CPU-friendly, completely free
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_BATCH_SIZE: int = 32

    # ── Vector Store ──────────────────────────────────────────────────────
    VECTOR_STORE_BACKEND: Literal["pgvector", "faiss"] = "pgvector"
    FAISS_INDEX_PATH: str = "./faiss_index"  # Only used if backend=faiss

    # ── File Storage ──────────────────────────────────────────────────────
    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 20
    ALLOWED_MIME_TYPES: str = "application/pdf,text/plain"

    # Supabase (only needed if STORAGE_BACKEND=supabase)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_BUCKET: str = "rag-documents"
    
    # ── Redis ───────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"   # 'redis' matches the docker-compose service name

    # ── Chunking ──────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 400       # tokens per chunk
    CHUNK_OVERLAP: int = 64     # overlap between consecutive chunks

    # ── Retrieval ─────────────────────────────────────────────────────────
    RETRIEVAL_TOP_K: int = 8            # chunks to retrieve per query
    RETRIEVAL_MIN_SIMILARITY: float = 0.10  # discard below this cosine score

    # ── Reranker ──────────────────────────────────────────────────────────
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_TOP_K: int = 5

    # ── Query Expansion ───────────────────────────────────────────────────
    QUERY_EXPANSION_ENABLED: bool = True
    QUERY_EXPANSION_VARIANTS: int = 3   # number of semantic variants to generate

    # ── Document Namespaces ───────────────────────────────────────────────
    DOC_NAMESPACE_FALLBACK_THRESHOLD: int = 2   # fall back to global if namespace returns fewer than this
    DOC_NAMESPACES: list[str] = ["resume", "technical", "research", "general"]

    # ── Critic Agent ──────────────────────────────────────────────────────
    CRITIC_CONFIDENCE_THRESHOLD: float = 0.6  # below = "unverified" label
    CRITIC_ENABLED: bool = True

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Data Retention ────────────────────────────────────────────────────
    DOCUMENT_RETENTION_DAYS: int = 30  # set 0 to disable

    # ── Observability ─────────────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"  # json=prod, text=dev

    # Add to your existing Settings class
    RAGAS_ENABLED: bool = True
    RAGAS_SAMPLE_SIZE: int = 3        # number of synthetic questions generated per doc
    RAGAS_MIN_CHUNK_WORDS: int = 30   # skip chunks shorter than this for question gen



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached Settings singleton via lru_cache(maxsize=1).

    WHY lru_cache over @cache:
      - @cache (functools.cache) has NO cache_clear() — impossible to reset in tests.
      - lru_cache(maxsize=1) is functionally identical for a no-arg function
        BUT exposes .cache_clear(), allowing test isolation via:
            get_settings.cache_clear()

    Usage everywhere in the app:
        from app.core.config import get_settings
        cfg = get_settings()
    """
    return Settings()


def clear_settings_cache() -> None:
    """
    Invalidates the cached Settings instance.

    Use in:
      - pytest fixtures (conftest.py) to isolate tests that mutate env vars
      - Health-check endpoints that need to verify live config state

    Example in conftest.py:
        @pytest.fixture(autouse=True)
        def reset_settings():
            yield
            clear_settings_cache()
    """
    get_settings.cache_clear()
