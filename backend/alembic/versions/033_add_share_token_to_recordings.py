"""Add share_token to recordings for public share links

Revision ID: 033
Revises: 032
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recordings", sa.Column("share_token", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_recordings_share_token", "recordings", ["share_token"])
    op.create_index(
        "ix_recordings_share_token",
        "recordings",
        ["share_token"],
        unique=True,
        postgresql_where=sa.text("share_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_recordings_share_token", table_name="recordings")
    op.drop_constraint("uq_recordings_share_token", "recordings", type_="unique")
    op.drop_column("recordings", "share_token")
