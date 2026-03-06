"""mvp sleep sessions and onboarding

Revision ID: 20260305_0003
Revises: 20260304_0002
Create Date: 2026-03-05 00:00:03
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260305_0003"
down_revision = "20260304_0002"
branch_labels = None
depends_on = None


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "users" in tables:
        user_columns = _column_names(inspector, "users")

        with op.batch_alter_table("users") as batch_op:
            if "share_token" not in user_columns:
                batch_op.add_column(sa.Column("share_token", sa.String(length=64), nullable=True))
            if "ronca_habitualmente" not in user_columns:
                batch_op.add_column(
                    sa.Column(
                        "ronca_habitualmente",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )
            if "cansancio_diurno" not in user_columns:
                batch_op.add_column(
                    sa.Column(
                        "cansancio_diurno",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )
            if "informed_consent_at" not in user_columns:
                batch_op.add_column(sa.Column("informed_consent_at", sa.DateTime(timezone=True), nullable=True))
            if "medical_disclaimer_accepted_at" not in user_columns:
                batch_op.add_column(
                    sa.Column("medical_disclaimer_accepted_at", sa.DateTime(timezone=True), nullable=True)
                )

        user_indexes = _index_names(inspector, "users")
        if "ix_users_share_token" not in user_indexes:
            op.create_index("ix_users_share_token", "users", ["share_token"], unique=True)

    if "sleep_sessions" not in tables:
        op.create_table(
            "sleep_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("snore_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("apnea_events", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("avg_oxygen", sa.Float(), nullable=True),
            sa.Column("ambient_noise_level", sa.Float(), nullable=True),
            sa.Column("sleep_score", sa.Integer(), nullable=True),
            sa.Column("continuity_timeline", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

        op.create_index("ix_sleep_sessions_user_id", "sleep_sessions", ["user_id"], unique=False)
        op.create_index("ix_sleep_sessions_start_time", "sleep_sessions", ["start_time"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "sleep_sessions" in tables:
        session_indexes = _index_names(inspector, "sleep_sessions")
        if "ix_sleep_sessions_start_time" in session_indexes:
            op.drop_index("ix_sleep_sessions_start_time", table_name="sleep_sessions")
        if "ix_sleep_sessions_user_id" in session_indexes:
            op.drop_index("ix_sleep_sessions_user_id", table_name="sleep_sessions")
        op.drop_table("sleep_sessions")

    if "users" in tables:
        user_indexes = _index_names(inspector, "users")
        if "ix_users_share_token" in user_indexes:
            op.drop_index("ix_users_share_token", table_name="users")

        user_columns = _column_names(inspector, "users")
        with op.batch_alter_table("users") as batch_op:
            if "medical_disclaimer_accepted_at" in user_columns:
                batch_op.drop_column("medical_disclaimer_accepted_at")
            if "informed_consent_at" in user_columns:
                batch_op.drop_column("informed_consent_at")
            if "cansancio_diurno" in user_columns:
                batch_op.drop_column("cansancio_diurno")
            if "ronca_habitualmente" in user_columns:
                batch_op.drop_column("ronca_habitualmente")
            if "share_token" in user_columns:
                batch_op.drop_column("share_token")
