# backend/migrations/versions/0002_resize_vector_1536.py
"""Resize embedding vector column from 384 to 1536 dimensions for text-embedding-3-small

Revision ID: 0002_resize_vector_1536
Revises: (your current revision id)
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_resize_vector_1536"
down_revision = "0002_fix_chunks_cascade"  # ← correct chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing IVFFlat index — it's dimension-specific
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx;")

    # Drop old vector column and recreate with new dimension
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding;")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1536);")

    # Recreate IVFFlat index for 1536-dim vectors
    # lists=100 is appropriate for up to ~500k vectors
    op.execute("""
        CREATE INDEX chunks_embedding_idx
        ON chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx;")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding;")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(384);")
    op.execute("""
        CREATE INDEX chunks_embedding_idx
        ON chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)
