"""add desaturation_count to sleep sessions

Revision ID: 20260820_0007
Revises: 20260819_0006
Create Date: 2026-08-20 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260820_0007"
down_revision = "20260819_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sleep_sessions",
        sa.Column("desaturation_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("sleep_sessions", "desaturation_count")