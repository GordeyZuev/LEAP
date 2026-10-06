"""Saved sort rule for playlist items and channel videos/playlists.

NULL means a hand-made order (drag / arrow keys). Existing rows start as NULL.

Revision ID: 060
Revises: 059
Create Date: 2026-10-05
"""

import sqlalchemy as sa

from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playlists", sa.Column("item_sort", sa.String(16), nullable=True))
    op.add_column("channels", sa.Column("video_sort", sa.String(16), nullable=True))
    op.add_column("channels", sa.Column("playlist_sort", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "playlist_sort")
    op.drop_column("channels", "video_sort")
    op.drop_column("playlists", "item_sort")
