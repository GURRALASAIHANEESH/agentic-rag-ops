import os
from pathlib import Path
from dotenv import load_dotenv

# Must be first: loads .env before app imports trigger get_settings()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

"""
Pytest configuration and shared fixtures.

All tests use an isolated in-memory SQLite database (via async engine)
so no running Postgres is required for unit/integration tests.
The LLM client is mocked by default — tests never call a real model.
"""
import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app


# ── Event loop (session-scoped for async fixtures) ────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """
    Single event loop for the entire test session.
    Required when using session-scoped async fixtures.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── In-memory test database ───────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    Creates a shared async SQLite engine for the test session.
    SQLite is used so tests run without a real Postgres instance.
    NOTE: pgvector-specific SQL (e.g. <=> operator) is skipped in unit tests.

    StaticPool is required for in-memory SQLite: without it each connection
    gets its own empty database, breaking rollback isolation between tests.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a fresh database session per test, rolled back after each test.
    Ensures tests are fully isolated with no state leakage.

    Key: we manually begin() and rollback() instead of using the context manager
    because calling rollback() inside `async with session.begin()` closes the
    transaction early and breaks subsequent ORM operations in the same test.
    """
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX AsyncClient wired to the FastAPI app.
    Overrides get_db to use the test session.
    """
    app = create_app()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Test users and tokens ─────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    """Creates a standard test user with a workspace."""
    from app.models.user import User, Workspace

    # Unique email per test invocation prevents UNIQUE constraint conflicts
    # even if a previous rollback didn't fully clear (e.g. on test error)
    unique_suffix = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        email=f"test_{unique_suffix}@ragops.dev",
        full_name="Test User",
        hashed_password=hash_password("TestPass1234"),
        role="user",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    workspace = Workspace(
        id=uuid.uuid4(),
        owner_id=user.id,
        name="Test Workspace",
        description="Workspace for test suite",
    )
    db.add(workspace)
    await db.flush()

    return {"user": user, "workspace": workspace}


@pytest.fixture
def auth_headers(test_user) -> dict:
    """
    Returns Authorization headers for the test user.
    Used in all authenticated endpoint tests.
    """
    user = test_user["user"]
    workspace = test_user["workspace"]
    token = create_access_token(
        subject=str(user.id),
        role=user.role,
        workspace_id=str(workspace.id),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict:
    """Returns Authorization headers for an admin user."""
    token = create_access_token(
        subject=str(uuid.uuid4()),
        role="admin",
    )
    return {"Authorization": f"Bearer {token}"}


# ── Mock LLM client ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm():
    """
    Mocked LLMClient that returns deterministic responses.
    Prevents any real network calls to LLM providers during tests.

    generate() returns a canned answer.
    stream() yields tokens from the same canned answer.
    """
    client = MagicMock()
    client.model_name = "mock-model"
    client.provider_name = "mock"

    canned_answer = (
        "Attention mechanisms allow models to focus on relevant parts "
        "of the input [SOURCE 1]. Self-attention computes query, key, "
        "and value vectors [SOURCE 2]."
    )

    client.generate = AsyncMock(return_value=canned_answer)

    async def mock_stream(prompt, system=""):
        for word in canned_answer.split():
            yield word + " "

    client.stream = mock_stream
    return client


# ── Mock embedding service ────────────────────────────────────────────────────

@pytest.fixture
def mock_embedder():
    """
    Returns a deterministic 384-dim zero vector.
    Avoids loading the sentence-transformers model during tests.
    """
    embedder = MagicMock()
    embedder.dimension = 384

    async def mock_embed_text(text: str):
        # Return a normalized non-zero vector so cosine similarity works
        import math
        vec = [0.1] * 384
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec]

    async def mock_embed_batch(texts):
        return [await mock_embed_text(t) for t in texts]

    def mock_cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        return round(dot, 4)

    embedder.embed_text = mock_embed_text
    embedder.embed_batch = mock_embed_batch
    embedder.cosine_similarity = mock_cosine_similarity
    return embedder


from app.core.config import clear_settings_cache


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure every test gets a fresh Settings read — no stale cache bleed."""
    clear_settings_cache()
    yield
    clear_settings_cache()
