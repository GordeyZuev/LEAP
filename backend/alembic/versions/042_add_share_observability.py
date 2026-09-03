"""Add share observability: events table and recording counters

Revision ID: 042
Revises: 041
Create Date: 2026-09-05
"""

import sqlalchemy as sa

from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("share_view_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "recordings",
        sa.Column("share_download_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "recordings",
        sa.Column("share_last_viewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recordings",
        sa.Column("share_last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "share_access_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("artifact_type", sa.String(32), nullable=True),
        sa.Column("visitor_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_share_access_events_recording_created",
        "share_access_events",
        ["recording_id", "created_at"],
    )
    op.create_index(
        "ix_share_access_events_dedup",
        "share_access_events",
        ["recording_id", "event_type", "visitor_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_share_access_events_dedup", table_name="share_access_events")
    op.drop_index("ix_share_access_events_recording_created", table_name="share_access_events")
    op.drop_table("share_access_events")
    op.drop_column("recordings", "share_last_downloaded_at")
    op.drop_column("recordings", "share_last_viewed_at")
    op.drop_column("recordings", "share_download_count")
    op.drop_column("recordings", "share_view_count")
