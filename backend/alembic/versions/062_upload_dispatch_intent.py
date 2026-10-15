"""Add preview recovery state and persist auto-upload dispatch.

Revision ID: 062
Revises: 061
Create Date: 2026-10-15
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("preview_maker_stages", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("preview_maker_stages", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE preview_maker_stages SET attempt_count = 1 WHERE run_token IS NOT NULL")
    op.execute("UPDATE preview_maker_stages SET queued_at = now() WHERE status = 'PENDING' AND queued_at IS NULL")
    op.create_index("ix_preview_maker_stages_status_started_at", "preview_maker_stages", ["status", "started_at"])
    op.create_index("ix_preview_maker_stages_status_queued_at", "preview_maker_stages", ["status", "queued_at"])
    op.create_index("ix_preview_maker_stages_status_failed_at", "preview_maker_stages", ["status", "failed_at"])

    op.add_column("output_targets", sa.Column("dispatch_task_id", sa.String(64), nullable=True))
    op.add_column("output_targets", sa.Column("dispatch_platform", sa.String(50), nullable=True))
    op.add_column("output_targets", sa.Column("dispatch_metadata_override", postgresql.JSONB(), nullable=True))
    op.add_column("output_targets", sa.Column("dispatch_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("output_targets", sa.Column("dispatch_published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("output_targets", sa.Column("dispatch_finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_output_targets_dispatch_task_id", "output_targets", ["dispatch_task_id"])
    op.create_index("ix_output_targets_dispatch_requested_at", "output_targets", ["dispatch_requested_at"])


def downgrade() -> None:
    op.drop_index("ix_output_targets_dispatch_requested_at", table_name="output_targets")
    op.drop_index("ix_output_targets_dispatch_task_id", table_name="output_targets")
    op.drop_column("output_targets", "dispatch_published_at")
    op.drop_column("output_targets", "dispatch_requested_at")
    op.drop_column("output_targets", "dispatch_metadata_override")
    op.drop_column("output_targets", "dispatch_platform")
    op.drop_column("output_targets", "dispatch_task_id")
    op.drop_column("output_targets", "dispatch_finished_at")
    op.drop_index("ix_preview_maker_stages_status_failed_at", table_name="preview_maker_stages")
    op.drop_index("ix_preview_maker_stages_status_queued_at", table_name="preview_maker_stages")
    op.drop_index("ix_preview_maker_stages_status_started_at", table_name="preview_maker_stages")
    op.drop_column("preview_maker_stages", "attempt_count")
    op.drop_column("preview_maker_stages", "queued_at")
