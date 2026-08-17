"""Add automation_job_runs for automation job run history

Revision ID: 034
Revises: 033
Create Date: 2026-08-16
"""

import sqlalchemy as sa

from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_job_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False, server_default="SCHEDULE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("synced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recordings_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["automation_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_job_runs_id", "automation_job_runs", ["id"])
    op.create_index("ix_automation_job_runs_job_id", "automation_job_runs", ["job_id"])
    op.create_index("ix_automation_job_runs_user_id", "automation_job_runs", ["user_id"])
    # The history view always reads one job's runs newest-first.
    op.create_index(
        "ix_automation_job_runs_job_started",
        "automation_job_runs",
        ["job_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_automation_job_runs_job_started", table_name="automation_job_runs")
    op.drop_index("ix_automation_job_runs_user_id", table_name="automation_job_runs")
    op.drop_index("ix_automation_job_runs_job_id", table_name="automation_job_runs")
    op.drop_index("ix_automation_job_runs_id", table_name="automation_job_runs")
    op.drop_table("automation_job_runs")
