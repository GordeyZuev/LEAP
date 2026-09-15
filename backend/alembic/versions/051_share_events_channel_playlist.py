"""Nullable share_access_events.recording_id plus playlist/channel subjects.

Revision ID: 051
Revises: 050
Create Date: 2026-09-15
"""

import sqlalchemy as sa

from alembic import op

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("share_access_events", "recording_id", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "share_access_events",
        sa.Column("playlist_id", sa.Integer(), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "share_access_events",
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_share_access_events_playlist_created", "share_access_events", ["playlist_id", "created_at"])
    op.create_index("ix_share_access_events_channel_created", "share_access_events", ["channel_id", "created_at"])
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                GRANT SELECT ON channels, channel_videos, channel_playlists TO grafana_ro;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                REVOKE SELECT ON channels, channel_videos, channel_playlists FROM grafana_ro;
            END IF;
        END
        $$;
        """
    )
    op.drop_index("ix_share_access_events_channel_created", table_name="share_access_events")
    op.drop_index("ix_share_access_events_playlist_created", table_name="share_access_events")
    op.drop_column("share_access_events", "channel_id")
    op.drop_column("share_access_events", "playlist_id")
    op.execute("DELETE FROM share_access_events WHERE recording_id IS NULL")
    op.alter_column("share_access_events", "recording_id", existing_type=sa.Integer(), nullable=False)
