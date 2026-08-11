"""add token_version to users and model_source to sleep_sessions

Revision ID: 20260810_0002
Revises: 20260728_0001
Create Date: 2026-08-10 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260810_0002"
down_revision = "20260728_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "sleep_sessions",
        sa.Column("model_source", sa.String(24), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sleep_sessions", "model_source")
    op.drop_column("users", "token_version")
