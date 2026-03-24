# backend/app/core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


# ── Alias for scripts that import AsyncSessionLocal directly ──────────────────
# seed_db.py, ingest_sample_docs.py use:
#   from app.core.database import AsyncSessionLocal
# This alias keeps those scripts working without modification.
AsyncSessionLocal = property(lambda self: get_session_factory())

# Simpler callable alias — scripts use it as: async with AsyncSessionLocal() as session
def AsyncSessionLocal():
    return get_session_factory()()


# ── FastAPI dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Yields an async DB session for FastAPI route dependencies.
    Commits on success, rolls back on exception, always closes.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── pgvector setup ────────────────────────────────────────────────────────────
async def ensure_pgvector_extension() -> None:
    """Creates pgvector + uuid-ossp extensions if they don't exist. Safe to call repeatedly."""
    async with get_engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    logger.info("pgvector and uuid-ossp extensions verified")


# ── Health check ──────────────────────────────────────────────────────────────
async def check_db_health() -> bool:
    """Returns True if Postgres is reachable. Used by /health endpoint."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
