"""Add needs_reauth flag and fix last_used_at tracking on user_credentials

Revision ID: 027
Revises: 026
Create Date: 2026-06-17

Adds needs_reauth BOOLEAN NOT NULL DEFAULT FALSE to user_credentials so that
failed upload authentication attempts can be surfaced in the UI as an
actionable "Re-auth needed" status.
"""

import sqlalchemy as sa

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_credentials",
        sa.Column("needs_reauth", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("user_credentials", "needs_reauth")
