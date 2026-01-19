"""Add soft delete to recordings table

Revision ID: 020
Revises: 019
Create Date: 2026-01-19 12:00:00.000000

Add deleted flag and deleted_at timestamp for soft delete functionality.
When user deletes recording, it's marked as deleted and expire_at is set to +3 days.
Physical deletion happens when expire_at is reached.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add deleted and deleted_at columns to recordings table."""
    op.add_column("recordings", sa.Column("deleted", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("recordings", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_recordings_deleted", "recordings", ["deleted"])


def downgrade() -> None:
    """Remove deleted and deleted_at columns from recordings table."""
    op.drop_index("ix_recordings_deleted", table_name="recordings")
    op.drop_column("recordings", "deleted_at")
    op.drop_column("recordings", "deleted")
