"""Add recordings.share_artifact_files JSONB cache for public share file list.

Revision ID: 052
Revises: 051
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("share_artifact_files", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recordings", "share_artifact_files")
