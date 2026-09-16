"""Nullable finished_at and one RUNNING run per job

Revision ID: 054
Revises: 053
Create Date: 2026-09-16
"""

import sqlalchemy as sa

from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "automation_job_runs",
        "finished_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.create_index(
        "uq_automation_job_runs_running",
        "automation_job_runs",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_automation_job_runs_running", table_name="automation_job_runs")
    op.execute("UPDATE automation_job_runs SET finished_at = started_at WHERE finished_at IS NULL")
    op.alter_column(
        "automation_job_runs",
        "finished_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
