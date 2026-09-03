"""Add PENDING_CONVERSION processing status

Revision ID: 041
Revises: 040
Create Date: 2026-09-04

MTS Link prepare-before-run: waiting for platform MP4 render without holding
a download worker. Apply before deploying code that writes PENDING_CONVERSION.
"""

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'PENDING_CONVERSION' AFTER 'PENDING_SOURCE'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly.
    pass
