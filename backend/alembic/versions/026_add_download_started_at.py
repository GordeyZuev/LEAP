"""Add download_started_at to recordings for download duration tracking

Revision ID: 026
Revises: 025
Create Date: 2026-06-14

Adds download_started_at alongside the existing downloaded_at so that
download duration can be computed (downloaded_at - download_started_at).
"""

import sqlalchemy as sa

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("download_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recordings", "download_started_at")
