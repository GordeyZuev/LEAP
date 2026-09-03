"""Add MTS_LINK source type

Revision ID: 040
Revises: 039
Create Date: 2026-09-03

Adds SourceType.MTS_LINK so MTS Link recordings can be persisted by sync.
Must be applied before deploying code that writes MTS_LINK rows.
"""

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'MTS_LINK'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly.
    # Value is left in place; to remove it, recreate the enum type.
    pass
