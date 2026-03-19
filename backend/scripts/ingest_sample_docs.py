#!/usr/bin/env python3
"""
Ingest all sample docs from backend/sample_docs/ into the demo workspace.

Usage (from backend/ directory):
    python scripts/ingest_sample_docs.py

Prerequisites:
    1. Postgres running (docker-compose up postgres)
    2. Database seeded (python scripts/seed_db.py)
    3. .env file present with DATABASE_URL

What it does:
    - Logs in as user@ragops.dev
    - Finds their default workspace
    - Ingests all 5 sample .txt files
    - Prints chunk counts and timing
"""
import asyncio
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, ensure_pgvector_extension
from app.models.user import User, Workspace
from app.models.document import Document
from app.services.ingestion import IngestionService
from app.models import *  # register all models

SAMPLE_DOCS_DIR = Path(__file__).parent.parent / "sample_docs"
DEMO_USER_EMAIL = "user@ragops.dev"


async def ingest_all():
    print("📥 Starting sample document ingestion...")
    await ensure_pgvector_extension()

    async with AsyncSessionLocal() as db:
        # ── Get demo user ─────────────────────────────────────────────────
        result = await db.execute(
            select(User).where(User.email == DEMO_USER_EMAIL)
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"❌ User {DEMO_USER_EMAIL} not found. Run seed_db.py first.")
            return

        # ── Get user's workspace ──────────────────────────────────────────
        ws_result = await db.execute(
            select(Workspace).where(Workspace.owner_id == user.id).limit(1)
        )
        workspace = ws_result.scalar_one_or_none()
        if not workspace:
            print("❌ No workspace found. Run seed_db.py first.")
            return

        print(f"  👤 User: {user.email}")
        print(f"  📁 Workspace: {workspace.name} (id={workspace.id})")
        print()

        service = IngestionService()
        sample_files = list(SAMPLE_DOCS_DIR.glob("*.txt"))

        if not sample_files:
            print(f"❌ No .txt files found in {SAMPLE_DOCS_DIR}")
            return

        total_chunks = 0

        for file_path in sample_files:
            file_bytes = file_path.read_bytes()
            safe_name = file_path.name

            # Check if already ingested (idempotent)
            existing = await db.execute(
                select(Document).where(
                    Document.workspace_id == workspace.id,
                    Document.filename == safe_name,
                )
            )
            if existing.scalar_one_or_none():
                print(f"  ⏭  {safe_name} already ingested, skipping.")
                continue

            # Create Document record
            doc = Document(
                workspace_id=workspace.id,
                filename=safe_name,
                file_size_bytes=len(file_bytes),
                mime_type="text/plain",
                storage_path=str(file_path),
                status="pending",
            )
            db.add(doc)
            await db.flush()

            # Run ingestion pipeline
            start = time.monotonic()
            print(f"  ⚙️  Ingesting: {safe_name} ({len(file_bytes)} bytes)...")

            try:
                chunks = await service.ingest_document(
                    db=db,
                    document_id=doc.id,
                    file_bytes=file_bytes,
                    mime_type="text/plain",
                    user_id=user.id,
                )
                elapsed = time.monotonic() - start
                total_chunks += chunks
                print(f"  ✅ {safe_name}: {chunks} chunks in {elapsed:.2f}s")
            except Exception as e:
                print(f"  ❌ {safe_name}: failed — {e}")

        await db.commit()

    print(f"\n✅ Ingestion complete. Total chunks created: {total_chunks}")
    print(f"\nYou can now run a query:")
    print(
        '  curl -X POST http://localhost:8000/api/query/sync \\\n'
        '    -H "Authorization: Bearer <token>" \\\n'
        '    -H "Content-Type: application/json" \\\n'
        '    -d \'{"query": "What is attention mechanism?", '
        f'"workspace_id": "{workspace.id if workspace else "<uuid>"}", "stream": false}}\''
    )


if __name__ == "__main__":
    asyncio.run(ingest_all())
