"""Channels, membership, and share_access_events subject columns.

Revision ID: 050
Revises: 049
Create Date: 2026-09-15
"""

import sqlalchemy as sa

from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("share_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("banner_key", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_channels_user_name"),
        sa.UniqueConstraint("slug", name="uq_channels_slug"),
    )
    op.create_index("ix_channels_user_id", "channels", ["user_id"])
    op.create_index("ix_channels_slug", "channels", ["slug"])
    op.create_index("ix_channels_user_updated", "channels", ["user_id", "updated_at"])

    op.create_table(
        "channel_videos",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("channel_id", "recording_id", name="uq_channel_videos_channel_recording"),
    )
    op.create_index("ix_channel_videos_channel_id", "channel_videos", ["channel_id"])
    op.create_index("ix_channel_videos_recording_id", "channel_videos", ["recording_id"])
    op.create_index("ix_channel_videos_channel_position", "channel_videos", ["channel_id", "position"])

    op.create_table(
        "channel_playlists",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("playlist_id", sa.Integer(), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("channel_id", "playlist_id", name="uq_channel_playlists_channel_playlist"),
    )
    op.create_index("ix_channel_playlists_channel_id", "channel_playlists", ["channel_id"])
    op.create_index("ix_channel_playlists_playlist_id", "channel_playlists", ["playlist_id"])
    op.create_index("ix_channel_playlists_channel_position", "channel_playlists", ["channel_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_channel_playlists_channel_position", table_name="channel_playlists")
    op.drop_index("ix_channel_playlists_playlist_id", table_name="channel_playlists")
    op.drop_index("ix_channel_playlists_channel_id", table_name="channel_playlists")
    op.drop_table("channel_playlists")
    op.drop_index("ix_channel_videos_channel_position", table_name="channel_videos")
    op.drop_index("ix_channel_videos_recording_id", table_name="channel_videos")
    op.drop_index("ix_channel_videos_channel_id", table_name="channel_videos")
    op.drop_table("channel_videos")
    op.drop_index("ix_channels_user_updated", table_name="channels")
    op.drop_index("ix_channels_slug", table_name="channels")
    op.drop_index("ix_channels_user_id", table_name="channels")
    op.drop_table("channels")
