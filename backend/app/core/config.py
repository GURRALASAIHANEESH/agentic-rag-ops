from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    """
    All configuration loaded from environment variables.
    .env file is auto-loaded in development.
    Never hardcode secrets here — use .env or GitHub Actions secrets.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
    WORKERS: int = 1                        # Increase to CPU count in production

    # ── Database (Postgres + pgvector) ────────────────────────────────────
    DATABASE_URL: str                       # e.g. postgresql+asyncpg://user:pass@localhost:5432/ragops
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── JWT Auth ──────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str                     # Min 32 chars — generate with: openssl rand -hex 32
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── LLM Provider toggle ───────────────────────────────────────────────
    # Set to "local" to use llama.cpp, "openai" to use OpenAI API
    LLM_PROVIDER: Literal["local", "openai", "groq"] = "local"

    # Local llama.cpp server (run via llm/run_server.sh)
    LLAMA_SERVER_URL: str = "http://localhost:8080"
    LLAMA_MODEL_NAME: str = "llama-3.2-3b-q4"
    LLAMA_MAX_TOKENS: int = 1024
    LLAMA_TEMPERATURE: float = 0.1          # Low temp = more deterministic = better for RAG

    # OpenAI (only needed if LLM_PROVIDER=openai)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"       # Cheapest capable model

    # Groq (only needed if LLM_PROVIDER=groq — free tier available)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # ── Embeddings ────────────────────────────────────────────────────────
    # all-MiniLM-L6-v2: 384-dim, ~80MB, CPU-friendly, free
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_BATCH_SIZE: int = 32

    # ── Vector Store ──────────────────────────────────────────────────────
    # "pgvector" = use Postgres (recommended), "faiss" = in-memory fallback
    VECTOR_STORE_BACKEND: Literal["pgvector", "faiss"] = "pgvector"
    FAISS_INDEX_PATH: str = "./faiss_index"  # Only used if backend=faiss

    # ── File Storage ──────────────────────────────────────────────────────
    # "local" = store uploads on disk, "supabase" = Supabase Storage free tier
    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 20            # Hard limit on PDF uploads
    ALLOWED_MIME_TYPES: str = "application/pdf,text/plain"

    # Supabase (only needed if STORAGE_BACKEND=supabase)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_BUCKET: str = "rag-documents"

    # ── Chunking ──────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512                   # tokens per chunk
    CHUNK_OVERLAP: int = 64                 # overlap between consecutive chunks

    # ── Retrieval ─────────────────────────────────────────────────────────
    RETRIEVAL_TOP_K: int = 5                # number of chunks to retrieve per query
    RETRIEVAL_MIN_SIMILARITY: float = 0.2   # discard chunks below this cosine score

    # ── Critic Agent ──────────────────────────────────────────────────────
    CRITIC_CONFIDENCE_THRESHOLD: float = 0.6  # below this = "unverified" label
    CRITIC_ENABLED: bool = True

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 30           # max requests per window
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Data Retention ────────────────────────────────────────────────────
    DOCUMENT_RETENTION_DAYS: int = 30       # demo default; set 0 to disable

    # ── Observability ─────────────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"  # json for prod, text for dev


def get_settings() -> Settings:
    """
    Cached singleton — import this everywhere instead of Settings() directly.
    Usage: from app.core.config import get_settings; cfg = get_settings()
    """
    return Settings()
