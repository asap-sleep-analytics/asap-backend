"""create waitlist leads

Revision ID: 20260304_0001
Revises: 
Create Date: 2026-03-04 00:00:01
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260304_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "waitlist_leads" in inspector.get_table_names():
        return

    lead_status = sa.Enum("pending", "confirmed", name="lead_status")
    lead_status.create(bind, checkfirst=True)

    op.create_table(
        "waitlist_leads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("device", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", lead_status, nullable=False, server_default="pending"),
        sa.Column("confirmation_token_hash", sa.String(length=64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_waitlist_leads_email", "waitlist_leads", ["email"], unique=True)
    op.create_index(
        "ix_waitlist_leads_confirmation_token_hash",
        "waitlist_leads",
        ["confirmation_token_hash"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "waitlist_leads" not in inspector.get_table_names():
        return

    op.drop_index("ix_waitlist_leads_confirmation_token_hash", table_name="waitlist_leads")
    op.drop_index("ix_waitlist_leads_email", table_name="waitlist_leads")
    op.drop_table("waitlist_leads")

    lead_status = sa.Enum("pending", "confirmed", name="lead_status")
    lead_status.drop(bind, checkfirst=True)
