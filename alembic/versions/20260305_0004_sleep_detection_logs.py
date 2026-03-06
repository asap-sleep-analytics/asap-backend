"""sleep detection confidence logs

Revision ID: 20260305_0004
Revises: 20260305_0003
Create Date: 2026-03-05 01:00:04
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260305_0004"
down_revision = "20260305_0003"
branch_labels = None
depends_on = None


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "sleep_detection_logs" not in tables:
        op.create_table(
            "sleep_detection_logs",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("window_index", sa.Integer(), nullable=False),
            sa.Column("start_second", sa.Float(), nullable=False),
            sa.Column("end_second", sa.Float(), nullable=False),
            sa.Column("label", sa.String(length=24), nullable=False),
            sa.Column("confidence_score", sa.Float(), nullable=False),
            sa.Column("model_source", sa.String(length=24), nullable=False),
            sa.Column("model_version", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["session_id"], ["sleep_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

        op.create_index("ix_sleep_detection_logs_session_id", "sleep_detection_logs", ["session_id"], unique=False)
        op.create_index("ix_sleep_detection_logs_created_at", "sleep_detection_logs", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "sleep_detection_logs" in tables:
        indexes = _index_names(inspector, "sleep_detection_logs")
        if "ix_sleep_detection_logs_created_at" in indexes:
            op.drop_index("ix_sleep_detection_logs_created_at", table_name="sleep_detection_logs")
        if "ix_sleep_detection_logs_session_id" in indexes:
            op.drop_index("ix_sleep_detection_logs_session_id", table_name="sleep_detection_logs")
        op.drop_table("sleep_detection_logs")
