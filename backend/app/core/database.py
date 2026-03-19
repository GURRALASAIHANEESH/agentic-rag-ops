from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Declarative base for all ORM models ──────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Async engine ─────────────────────────────────────────────────────────────
# pool_pre_ping=True: drops stale connections before using them (important for
# long-running containers that outlive Postgres restarts)
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.DEBUG,       # logs all SQL when DEBUG=true
)


# ── Session factory ───────────────────────────────────────────────────────────
# expire_on_commit=False: keeps ORM objects usable after commit (needed for
# async code where lazy loads would fail outside a session context)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Yields an async DB session for use in FastAPI route dependencies.
    Always rolls back on exception and closes session on exit.

    Usage in routes:
        async def my_route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── pgvector setup helper ─────────────────────────────────────────────────────
async def ensure_pgvector_extension() -> None:
    """
    Creates the pgvector extension if it doesn't exist.
    Called once during app startup — safe to call multiple times.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        logger.info("pgvector and uuid-ossp extensions verified")


# ── Health check helper ───────────────────────────────────────────────────────
async def check_db_health() -> bool:
    """
    Returns True if Postgres is reachable. Used by /health endpoint.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
