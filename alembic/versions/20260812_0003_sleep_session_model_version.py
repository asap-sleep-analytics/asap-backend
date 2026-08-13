"""add model_version to sleep_sessions

Revision ID: 20260812_0003
Revises: 20260810_0002
Create Date: 2026-08-12 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260812_0003"
down_revision = "20260810_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sleep_sessions",
        sa.Column("model_version", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sleep_sessions", "model_version")