"""add_pause_fields

Revision ID: 011
Revises: 010
Create Date: 2026-02-05

Add on_pause and pause_requested_at fields to recordings table
for deterministic pause/resume mechanism.
"""

import sqlalchemy as sa

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recordings", sa.Column("on_pause", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("recordings", sa.Column("pause_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("recordings", "pause_requested_at")
    op.drop_column("recordings", "on_pause")
