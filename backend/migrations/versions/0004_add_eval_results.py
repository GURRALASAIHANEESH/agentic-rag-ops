# migrations/versions/0004_add_eval_results.py
"""add eval_results table

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004"
down_revision = "0003_resize_vector_768"    # ← actual latest migration ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_results",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id",      UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("workspace_id",     UUID(as_uuid=True), nullable=False),
        sa.Column("question",         sa.Text(),          nullable=False),
        sa.Column("generated_answer", sa.Text(),          nullable=False),
        sa.Column("context_chunks",   JSONB(),            nullable=False),
        sa.Column("faithfulness",     sa.Float(),         nullable=True),
        sa.Column("answer_relevancy", sa.Float(),         nullable=True),
        sa.Column("context_precision",sa.Float(),         nullable=True),
        sa.Column("llm_provider",     sa.String(50),      nullable=False),
        sa.Column("eval_model",       sa.String(100),     nullable=False),
        sa.Column("raw_scores",       JSONB(),            nullable=False,
                  server_default="{}"),
        sa.Column("created_at",       sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_index("ix_eval_results_document_id",  "eval_results", ["document_id"])
    op.create_index("ix_eval_results_workspace_id", "eval_results", ["workspace_id"])
    op.create_index("ix_eval_results_created_at",   "eval_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_created_at",   table_name="eval_results")
    op.drop_index("ix_eval_results_workspace_id", table_name="eval_results")
    op.drop_index("ix_eval_results_document_id",  table_name="eval_results")
    op.drop_table("eval_results")
