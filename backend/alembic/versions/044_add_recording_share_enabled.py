"""Add recordings.share_enabled for Enable / Disable / Rotate

Revision ID: 044
Revises: 043
Create Date: 2026-09-05
"""

import sqlalchemy as sa

from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("share_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute("UPDATE recordings SET share_enabled = true WHERE share_token IS NOT NULL")


def downgrade() -> None:
    op.drop_column("recordings", "share_enabled")
