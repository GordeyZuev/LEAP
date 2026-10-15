"""Record the optional PREVIEW_MAKER stage without changing required-stage enums.

Revision ID: 061
Revises: 060
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preview_maker_stages",
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("recordings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("run_token", sa.String(64), nullable=True),
        sa.Column("source_video_path", sa.String(1000), nullable=True),
        sa.Column("source_trimmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.String(1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("preview_maker_stages")
