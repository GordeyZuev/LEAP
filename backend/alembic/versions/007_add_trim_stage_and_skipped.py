"""Add TRIM stage and SKIPPED status

Revision ID: 007
Revises: 006
Create Date: 2026-01-28 00:00:00.000000

Changes:
- Add skip_reason column to processing_stages table
- Update recordings: TRANSCRIBING → PROCESSING, TRANSCRIBED/PREPARING → PROCESSED
- BUG: TRIM was NOT added to processingstagetype PG enum here (fixed in migration 014)

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add skip_reason column to processing_stages
    op.add_column("processing_stages", sa.Column("skip_reason", sa.String(500), nullable=True))

    # 2. Update aggregate statuses in recordings
    op.execute("""
        UPDATE recordings
        SET status = 'PROCESSING'
        WHERE status = 'TRANSCRIBING'
    """)

    op.execute("""
        UPDATE recordings
        SET status = 'PROCESSED'
        WHERE status IN ('TRANSCRIBED', 'PREPARING')
    """)


def downgrade() -> None:
    # 1. Revert aggregate statuses in recordings
    op.execute("""
        UPDATE recordings
        SET status = 'TRANSCRIBING'
        WHERE status = 'PROCESSING'
    """)

    op.execute("""
        UPDATE recordings
        SET status = 'TRANSCRIBED'
        WHERE status = 'PROCESSED'
    """)

    # 2. Remove skip_reason column from processing_stages
    op.drop_column("processing_stages", "skip_reason")
