"""Widen video_file_size from INTEGER to BIGINT to support files > 2 GB.

Revision ID: 020
Revises: 019
Create Date: 2026-04-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "recordings",
        "video_file_size",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "recordings",
        "video_file_size",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
