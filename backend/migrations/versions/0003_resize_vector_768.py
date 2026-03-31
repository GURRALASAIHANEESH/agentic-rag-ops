"""Resize embedding vector column to 768 dimensions for nomic-embed-text-v1.5

Revision ID: 0003_resize_vector_768
Revises: 0002_fix_chunks_cascade
Create Date: 2026-03-24
"""
from alembic import op

revision = "0003_resize_vector_768"
down_revision = "0002_resize_vector_1536"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx;")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding;")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(768);")
    op.execute("""
        CREATE INDEX chunks_embedding_idx
        ON chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx;")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding;")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1536);")
    op.execute("""
        CREATE INDEX chunks_embedding_idx
        ON chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)
