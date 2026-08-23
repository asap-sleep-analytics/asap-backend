"""add composite indexes for list and pagination queries

Revision ID: 20260819_0005
Revises: 20260819_0004
Create Date: 2026-08-19 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260819_0005"
down_revision = "20260819_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sleep_detection_logs_session_window",
        "sleep_detection_logs",
        ["session_id", "window_index"],
    )
    op.create_index(
        "ix_sleep_sessions_user_start",
        "sleep_sessions",
        ["user_id", sa.text("start_time DESC")],
    )
    op.create_index(
        "ix_waitlist_leads_created_id",
        "waitlist_leads",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_waitlist_leads_created_id", table_name="waitlist_leads")
    op.drop_index("ix_sleep_sessions_user_start", table_name="sleep_sessions")
    op.drop_index("ix_sleep_detection_logs_session_window", table_name="sleep_detection_logs")
