"""add social auth fields and terms acceptance to users

Revision ID: 20260819_0004
Revises: 20260812_0003
Create Date: 2026-08-19 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260819_0004"
down_revision = "20260812_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(16),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column(
        "users",
        sa.Column("social_subject", sa.String(128), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_social_subject", "users", ["social_subject"])


def downgrade() -> None:
    op.drop_index("ix_users_social_subject", table_name="users")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "social_subject")
    op.drop_column("users", "auth_provider")
