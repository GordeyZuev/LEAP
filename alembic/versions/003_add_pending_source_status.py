"""Add PENDING_SOURCE status to ProcessingStatus enum

Revision ID: 003
Revises: 002
Create Date: 2026-01-22

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add PENDING_SOURCE status to ProcessingStatus enum.

    Note: Data migration (updating existing SKIPPED records to PENDING_SOURCE)
    should be done in a separate migration or manually after this migration completes,
    due to PostgreSQL's constraint that new enum values must be committed before use.
    """
    # Add PENDING_SOURCE to enum (PostgreSQL specific)
    op.execute(
        "ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'PENDING_SOURCE' BEFORE 'INITIALIZED'"
    )

    # Note: Cannot update existing records in the same transaction due to PostgreSQL limitations.
    # If needed, run this UPDATE manually after the migration:
    #
    # UPDATE recordings r
    # SET status = 'PENDING_SOURCE', blank_record = false
    # FROM source_metadata sm
    # WHERE r.id = sm.recording_id
    #   AND r.status = 'SKIPPED'
    #   AND sm.metadata->>'zoom_processing_incomplete' = 'true'
    #   AND r.deleted = false;


def downgrade() -> None:
    """Revert PENDING_SOURCE records back to SKIPPED."""
    # Move PENDING_SOURCE records back to SKIPPED
    op.execute("""
        UPDATE recordings
        SET status = 'SKIPPED'
        WHERE status = 'PENDING_SOURCE'
    """)

    # Note: Cannot remove enum value in PostgreSQL without recreating the type
    # This is acceptable as the enum value won't cause issues even if unused
