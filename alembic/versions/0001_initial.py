"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("analysis_id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("honesty_mode", sa.String(length=20), nullable=False),
        sa.Column("output_targets", sa.Text(), nullable=False),
        sa.Column("include_private", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
    )
    op.create_index("ix_analyses_username", "analyses", ["username"])
    op.create_index("ix_analyses_idempotency_key", "analyses", ["idempotency_key"])

    op.create_table(
        "oauth_tokens",
        sa.Column("username", sa.String(length=255), primary_key=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(length=255), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_states_username", "oauth_states", ["username"])
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oauth_states_expires_at", table_name="oauth_states")
    op.drop_index("ix_oauth_states_username", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_table("oauth_tokens")
    op.drop_index("ix_analyses_idempotency_key", table_name="analyses")
    op.drop_index("ix_analyses_username", table_name="analyses")
    op.drop_table("analyses")
