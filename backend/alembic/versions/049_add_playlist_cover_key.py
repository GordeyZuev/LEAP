"""Add playlists.cover_key for custom course covers.

Revision ID: 049
Revises: 048
Create Date: 2026-09-15
"""

import sqlalchemy as sa

from alembic import op

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playlists", sa.Column("cover_key", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("playlists", "cover_key")
