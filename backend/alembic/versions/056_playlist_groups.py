"""Named group folders within playlists.

Revision ID: 056
Revises: 055
Create Date: 2026-10-02
"""

import sqlalchemy as sa

from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playlist_groups",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("playlist_id", sa.Integer(), sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("playlist_id", "name", name="uq_playlist_groups_playlist_name"),
    )
    op.create_index("ix_playlist_groups_playlist_position", "playlist_groups", ["playlist_id", "position"])
    op.add_column("playlist_items", sa.Column("group_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_playlist_items_group_id", "playlist_items", "playlist_groups", ["group_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_playlist_items_group_id", "playlist_items", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_playlist_items_group_id", table_name="playlist_items")
    op.drop_constraint("fk_playlist_items_group_id", "playlist_items", type_="foreignkey")
    op.drop_column("playlist_items", "group_id")
    op.drop_index("ix_playlist_groups_playlist_position", table_name="playlist_groups")
    op.drop_table("playlist_groups")
