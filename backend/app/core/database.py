# backend/app/core/database.py

from __future__ import annotations

import sys
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_IN_CELERY = "celery" in sys.argv[0]


class Base(DeclarativeBase):
    pass


# ── Engine factory ────────────────────────────────────────────────────────────

def _make_engine():
    """
    Creates a fresh AsyncEngine.

    Celery workers:  NullPool — no connection is held across asyncio.run() calls.
                     Called fresh on every task invocation.
    FastAPI process: QueuePool (default) with pool_size/max_overflow from config.
                     Called once at startup, reused for the process lifetime.
    """
    settings = get_settings()

    if _IN_CELERY:
        from sqlalchemy.pool import NullPool
        return create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            pool_pre_ping=False,   # NullPool opens/closes per-use — pre_ping is redundant
            echo=settings.DEBUG,
        )
    else:
        return create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )


# ── FastAPI process: single engine for the process lifetime ───────────────────

_fastapi_engine = None
_fastapi_session_factory = None


def get_engine():
    """
    FastAPI path: returns the process-lifetime engine singleton.
    Celery path:  always returns a fresh engine (called per-task via get_async_session).
    """
    if _IN_CELERY:
        # Never cache in Celery — each call gets a fresh engine for the current loop
        return _make_engine()

    global _fastapi_engine
    if _fastapi_engine is None:
        _fastapi_engine = _make_engine()
    return _fastapi_engine


def get_session_factory():
    """
    FastAPI path: returns the process-lifetime session factory singleton.
    Celery path:  builds a fresh factory from a fresh engine (called per-task).
    """
    if _IN_CELERY:
        return async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    global _fastapi_session_factory
    if _fastapi_session_factory is None:
        _fastapi_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _fastapi_session_factory


# ── Celery worker helpers ─────────────────────────────────────────────────────

def init_db_engine() -> None:
    """
    Called once via @worker_process_init signal.
    In Celery mode get_engine() is always fresh, so this is a no-op kept
    for backwards compatibility with the signal registration in ingestion_worker.py.
    """
    pass  # intentional — Celery path never caches the engine


def get_async_session():
    """
    Returns a bare AsyncSession (not a context manager).
    Used by ingestion_worker._async_ingest() inside asyncio.run():

        async with get_async_session() as db:
            await service.ingest_document(db=db, ...)

    In Celery mode, every call to get_session_factory() returns a factory
    bound to a brand-new engine — so each asyncio.run() gets its own
    connection, fully isolated from all other tasks and loops.
    """
    return get_session_factory()()


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:
    """
    Yields an AsyncSession for FastAPI route dependencies.
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


# ── AsyncSessionLocal alias ───────────────────────────────────────────────────

def AsyncSessionLocal():
    """Callable alias for seed_db.py and ingest_sample_docs.py."""
    return get_session_factory()()


# ── pgvector setup ────────────────────────────────────────────────────────────

async def ensure_pgvector_extension() -> None:
    """Creates pgvector + uuid-ossp extensions if they don't exist."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    if _IN_CELERY:
        await engine.dispose()
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