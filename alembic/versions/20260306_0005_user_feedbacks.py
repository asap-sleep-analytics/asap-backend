"""create user feedbacks table

Revision ID: 20260306_0005
Revises: 20260305_0004
Create Date: 2026-03-06 00:05:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0005"
down_revision = "20260305_0004"
branch_labels = None
depends_on = None


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "user_feedbacks" not in tables:
        op.create_table(
            "user_feedbacks",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("sleep_rating", sa.Integer(), nullable=False),
            sa.Column("woke_tired", sa.Boolean(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["session_id"], ["sleep_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "user_id", name="uq_user_feedbacks_session_user"),
        )

        op.create_index("ix_user_feedbacks_session_id", "user_feedbacks", ["session_id"], unique=False)
        op.create_index("ix_user_feedbacks_user_id", "user_feedbacks", ["user_id"], unique=False)
        op.create_index("ix_user_feedbacks_created_at", "user_feedbacks", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "user_feedbacks" in tables:
        indexes = _index_names(inspector, "user_feedbacks")
        if "ix_user_feedbacks_created_at" in indexes:
            op.drop_index("ix_user_feedbacks_created_at", table_name="user_feedbacks")
        if "ix_user_feedbacks_user_id" in indexes:
            op.drop_index("ix_user_feedbacks_user_id", table_name="user_feedbacks")
        if "ix_user_feedbacks_session_id" in indexes:
            op.drop_index("ix_user_feedbacks_session_id", table_name="user_feedbacks")
        op.drop_table("user_feedbacks")
