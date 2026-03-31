# migrations/versions/0005_add_workspace_rate_limits.py
"""add rate limit columns to workspaces

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "rate_limit_rpm",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "rate_limit_daily",
            sa.Integer(),
            nullable=False,
            server_default="1000",
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "rate_limit_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "rate_limit_enabled")
    op.drop_column("workspaces", "rate_limit_daily")
    op.drop_column("workspaces", "rate_limit_rpm")
