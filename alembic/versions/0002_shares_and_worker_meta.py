"""shares and worker metadata

Revision ID: 0002_shares_and_worker_meta
Revises: 0001_initial
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_shares_and_worker_meta"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("analyses", sa.Column("failure_reason", sa.Text(), nullable=False, server_default=""))
    op.add_column("analyses", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analyses", sa.Column("last_duration_ms", sa.Float(), nullable=False, server_default="0"))

    op.create_table(
        "shares",
        sa.Column("token_id", sa.String(length=64), primary_key=True),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shares_analysis_id", "shares", ["analysis_id"])
    op.create_index("ix_shares_expires_at", "shares", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_shares_expires_at", table_name="shares")
    op.drop_index("ix_shares_analysis_id", table_name="shares")
    op.drop_table("shares")

    op.drop_column("analyses", "last_duration_ms")
    op.drop_column("analyses", "next_attempt_at")
    op.drop_column("analyses", "failure_reason")
    op.drop_column("analyses", "attempts")
