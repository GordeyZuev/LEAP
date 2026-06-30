"""Add usage_events table for action history and analytics

Revision ID: 030
Revises: 029
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("bytes_delta", sa.BigInteger(), nullable=True),
        sa.Column("event_metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_usage_events_user_id_created", "usage_events", ["user_id", "created_at"])
    op.create_index("ix_usage_events_event_type", "usage_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_event_type", table_name="usage_events")
    op.drop_index("ix_usage_events_user_id_created", table_name="usage_events")
    op.drop_table("usage_events")
