"""initial squash — all tables in one migration

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waitlist_leads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("device", sa.String(20), nullable=False),
        sa.Column("source", sa.String(80), nullable=False, server_default="landing-page"),
        sa.Column(
            "status",
            sa.Enum("pending", "confirmed", name="lead_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("confirmation_token_hash", sa.String(64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_waitlist_leads_email", "waitlist_leads", ["email"], unique=True)
    op.create_index("ix_waitlist_leads_confirmation_token_hash", "waitlist_leads", ["confirmation_token_hash"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("share_token", sa.String(64), nullable=True),
        sa.Column("ronca_habitualmente", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cansancio_diurno", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("informed_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("medical_disclaimer_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_share_token", "users", ["share_token"], unique=True)

    op.create_table(
        "sleep_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snore_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("apnea_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_oxygen", sa.Float(), nullable=True),
        sa.Column("ambient_noise_level", sa.Float(), nullable=True),
        sa.Column("sleep_score", sa.Integer(), nullable=True),
        sa.Column("continuity_timeline", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sleep_sessions_user_id", "sleep_sessions", ["user_id"])

    op.create_table(
        "sleep_detection_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sleep_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_index", sa.Integer(), nullable=False),
        sa.Column("start_second", sa.Float(), nullable=False),
        sa.Column("end_second", sa.Float(), nullable=False),
        sa.Column("label", sa.String(24), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("model_source", sa.String(24), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sleep_detection_logs_session_id", "sleep_detection_logs", ["session_id"])

    op.create_table(
        "user_feedbacks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sleep_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sleep_rating", sa.Integer(), nullable=False),
        sa.Column("woke_tired", sa.Boolean(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "user_id", name="uq_user_feedbacks_session_user"),
    )
    op.create_index("ix_user_feedbacks_session_id", "user_feedbacks", ["session_id"])
    op.create_index("ix_user_feedbacks_user_id", "user_feedbacks", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_feedbacks")
    op.drop_table("sleep_detection_logs")
    op.drop_table("sleep_sessions")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS lead_status")
    op.drop_table("waitlist_leads")
