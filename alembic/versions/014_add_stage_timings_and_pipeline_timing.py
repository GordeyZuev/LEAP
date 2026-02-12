"""Add stage_timings table and pipeline timing columns

Revision ID: 014
Revises: 013
Create Date: 2026-02-12

New stage_timings table for append-only audit/analytics of pipeline stage durations.
Add started_at to processing_stages and output_targets.
Add pipeline timing columns to recordings.
Add DOWNLOAD to processingstagetype enum.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add DOWNLOAD and TRIM to processingstagetype enum
    # TRIM was missed in migration 007 (incorrect assumption about PG enums)
    op.execute("ALTER TYPE processingstagetype ADD VALUE IF NOT EXISTS 'TRIM'")
    op.execute("ALTER TYPE processingstagetype ADD VALUE IF NOT EXISTS 'DOWNLOAD'")

    # --- New table: stage_timings ---
    op.create_table(
        "stage_timings",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("recording_id", sa.Integer, sa.ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("stage_type", sa.String(50), nullable=False),
        sa.Column("substep", sa.String(100), nullable=True),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_stage_timings_recording_id", "stage_timings", ["recording_id"])
    op.create_index("ix_stage_timings_user_id", "stage_timings", ["user_id"])
    op.create_index("ix_stage_timings_stage_type", "stage_timings", ["stage_type"])
    op.create_index("ix_stage_timings_recording_stage", "stage_timings", ["recording_id", "stage_type"])

    # --- Add started_at to processing_stages ---
    op.add_column("processing_stages", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))

    # --- Add started_at to output_targets ---
    op.add_column("output_targets", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))

    # --- Add pipeline timing to recordings ---
    op.add_column("recordings", sa.Column("pipeline_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recordings", sa.Column("pipeline_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recordings", sa.Column("pipeline_duration_seconds", sa.Float, nullable=True))


def downgrade() -> None:
    # Drop pipeline timing from recordings
    op.drop_column("recordings", "pipeline_duration_seconds")
    op.drop_column("recordings", "pipeline_completed_at")
    op.drop_column("recordings", "pipeline_started_at")

    # Drop started_at from output_targets
    op.drop_column("output_targets", "started_at")

    # Drop started_at from processing_stages
    op.drop_column("processing_stages", "started_at")

    # Drop stage_timings table
    op.drop_index("ix_stage_timings_recording_stage", table_name="stage_timings")
    op.drop_index("ix_stage_timings_stage_type", table_name="stage_timings")
    op.drop_index("ix_stage_timings_user_id", table_name="stage_timings")
    op.drop_index("ix_stage_timings_recording_id", table_name="stage_timings")
    op.drop_table("stage_timings")

    # Note: DOWNLOAD enum value cannot be removed from PostgreSQL enum without recreating the type
