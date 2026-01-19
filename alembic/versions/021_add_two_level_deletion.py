"""Add two-level deletion system to recordings

Revision ID: 021
Revises: 020
Create Date: 2026-01-19 18:00:00.000000

Add delete_state, deletion_reason, soft_deleted_at, hard_delete_at fields.
Implements two-level deletion: soft delete (files cleanup) and hard delete (DB removal).
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add two-level deletion fields and indexes."""
    # Add deletion tracking fields
    op.add_column("recordings", sa.Column("delete_state", sa.String(20), server_default="active", nullable=False))
    op.add_column("recordings", sa.Column("deletion_reason", sa.String(20), nullable=True))
    op.add_column("recordings", sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recordings", sa.Column("hard_delete_at", sa.DateTime(timezone=True), nullable=True))

    # Add single column indexes
    op.create_index("ix_recordings_delete_state", "recordings", ["delete_state"])
    op.create_index("ix_recordings_soft_deleted_at", "recordings", ["soft_deleted_at"])
    op.create_index("ix_recordings_hard_delete_at", "recordings", ["hard_delete_at"])

    # Add composite indexes for maintenance queries
    op.create_index("ix_recordings_delete_state_deleted_at", "recordings", ["delete_state", "deleted_at"])
    op.create_index("ix_recordings_deleted_expire_at", "recordings", ["deleted", "expire_at"])


def downgrade() -> None:
    """Remove two-level deletion fields and indexes."""
    # Drop indexes
    op.drop_index("ix_recordings_deleted_expire_at", table_name="recordings")
    op.drop_index("ix_recordings_delete_state_deleted_at", table_name="recordings")
    op.drop_index("ix_recordings_hard_delete_at", table_name="recordings")
    op.drop_index("ix_recordings_soft_deleted_at", table_name="recordings")
    op.drop_index("ix_recordings_delete_state", table_name="recordings")

    # Drop columns
    op.drop_column("recordings", "hard_delete_at")
    op.drop_column("recordings", "soft_deleted_at")
    op.drop_column("recordings", "deletion_reason")
    op.drop_column("recordings", "delete_state")
