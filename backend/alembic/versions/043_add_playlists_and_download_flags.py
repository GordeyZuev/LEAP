"""Add playlists, playlist items, and recording download flags

Revision ID: 043
Revises: 042
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("allow_video_download", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "recordings",
        sa.Column("allow_files_download", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("share_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("share_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("share_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_playlists_user_name"),
        sa.UniqueConstraint("share_token", name="uq_playlists_share_token"),
    )
    op.create_index(
        "ix_playlists_share_token",
        "playlists",
        ["share_token"],
        postgresql_where=sa.text("share_token IS NOT NULL"),
    )

    op.create_table(
        "playlist_items",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column(
            "playlist_id",
            sa.Integer(),
            sa.ForeignKey("playlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recording_id",
            sa.Integer(),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("playlist_id", "recording_id", name="uq_playlist_items_playlist_recording"),
    )
    op.create_index("ix_playlist_items_playlist_id", "playlist_items", ["playlist_id"])
    op.create_index("ix_playlist_items_recording_id", "playlist_items", ["recording_id"])
    op.create_index("ix_playlist_items_playlist_position", "playlist_items", ["playlist_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_playlist_items_playlist_position", table_name="playlist_items")
    op.drop_index("ix_playlist_items_recording_id", table_name="playlist_items")
    op.drop_index("ix_playlist_items_playlist_id", table_name="playlist_items")
    op.drop_table("playlist_items")
    op.drop_index("ix_playlists_share_token", table_name="playlists")
    op.drop_table("playlists")
    op.drop_column("recordings", "allow_files_download")
    op.drop_column("recordings", "allow_video_download")
