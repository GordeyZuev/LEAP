"""Refactor automation jobs

Revision ID: 006
Revises: 005
Create Date: 2026-01-27 00:00:00.000000

Changes:
- Remove source_id column (sources now extracted from templates)
- Remove allow_skipped from sync_config
- Change processing_config to nullable override dict
- Add filters column for recording selection
- Remove server_default from sync_config (defaults handled by application)

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Remove source_id column if it exists
    # Note: source_id column might have been removed in earlier migrations
    # Use batch to handle column that may not exist
    with op.batch_alter_table("automation_jobs", schema=None) as batch_op:
        # Check if column exists
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        columns = [c["name"] for c in inspector.get_columns("automation_jobs")]

        if "source_id" in columns:
            batch_op.drop_column("source_id")

    # 2. Update sync_config - remove allow_skipped and remove server_default
    op.execute("""
        UPDATE automation_jobs
        SET sync_config = sync_config - 'allow_skipped'
        WHERE sync_config ? 'allow_skipped'
    """)

    op.alter_column(
        "automation_jobs",
        "sync_config",
        server_default=None,
        existing_type=postgresql.JSONB,
        existing_nullable=False,
    )

    # 3. Change processing_config to nullable override dict (clear existing values)
    op.execute("""
        UPDATE automation_jobs
        SET processing_config = NULL
    """)

    op.alter_column(
        "automation_jobs",
        "processing_config",
        nullable=True,
        server_default=None,
        existing_type=postgresql.JSONB,
    )

    # 4. Add filters column
    op.add_column("automation_jobs", sa.Column("filters", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    # 1. Add source_id back (set to NULL for all existing records)
    op.add_column("automation_jobs", sa.Column("source_id", sa.Integer(), nullable=True))

    # Note: Foreign key constraint not restored automatically
    # Users need to manually set source_id values before constraint can be restored

    # 2. Restore old sync_config default
    op.alter_column(
        "automation_jobs",
        "sync_config",
        server_default='{"sync_days": 2, "allow_skipped": false}',
        existing_type=postgresql.JSONB,
        existing_nullable=False,
    )

    # 3. Restore old processing_config default
    op.alter_column(
        "automation_jobs",
        "processing_config",
        nullable=False,
        server_default='{"auto_process": true, "auto_upload": true, "max_parallel": 3}',
        existing_type=postgresql.JSONB,
    )

    op.execute("""
        UPDATE automation_jobs
        SET processing_config = '{"auto_process": true, "auto_upload": true, "max_parallel": 3}'::jsonb
        WHERE processing_config IS NULL
    """)

    # 4. Remove filters column
    op.drop_column("automation_jobs", "filters")
