"""Add LEAP to targettype enum

Revision ID: 048
Revises: 047
Create Date: 2026-09-11
"""

from alembic import op

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE targettype ADD VALUE IF NOT EXISTS 'LEAP'")


def downgrade() -> None:
    pass
