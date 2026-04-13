"""create_celery_beat_tables

Revision ID: 008
Revises: 007
Create Date: 2026-01-31

Creates tables for celery-sqlalchemy-scheduler:
- celery_interval_schedule
- celery_crontab_schedule
- celery_solar_schedule
- celery_periodic_task
- celery_periodic_task_changed

Also removes old incorrect celery_schedule table from migration 001.
"""

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old incorrect table if exists (from migration 001)
    op.execute("DROP TABLE IF EXISTS celery_schedule CASCADE")

    # 1. Interval Schedule (every N seconds/minutes/hours/days)
    op.create_table(
        "celery_interval_schedule",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("every", sa.Integer, nullable=False),
        sa.Column("period", sa.String(24), nullable=False),
    )

    # 2. Crontab Schedule (cron expressions)
    op.create_table(
        "celery_crontab_schedule",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("minute", sa.String(240), nullable=False, server_default="*"),
        sa.Column("hour", sa.String(96), nullable=False, server_default="*"),
        sa.Column("day_of_week", sa.String(64), nullable=False, server_default="*"),
        sa.Column("day_of_month", sa.String(124), nullable=False, server_default="*"),
        sa.Column("month_of_year", sa.String(64), nullable=False, server_default="*"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
    )

    # 3. Solar Schedule (sunrise/sunset events)
    op.create_table(
        "celery_solar_schedule",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event", sa.String(24), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
    )

    # 4. Periodic Task Changed (tracking updates)
    op.create_table(
        "celery_periodic_task_changed",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("last_update", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 5. Periodic Task (main table for scheduled tasks)
    op.create_table(
        "celery_periodic_task",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("task", sa.String(255), nullable=False),
        # Foreign keys to schedule tables (nullable, one of them should be set)
        sa.Column("interval_id", sa.Integer, nullable=True),
        sa.Column("crontab_id", sa.Integer, nullable=True),
        sa.Column("solar_id", sa.Integer, nullable=True),
        # Task parameters
        sa.Column("args", sa.Text, nullable=False, server_default="[]"),
        sa.Column("kwargs", sa.Text, nullable=False, server_default="{}"),
        # Queue settings
        sa.Column("queue", sa.String(255), nullable=True),
        sa.Column("exchange", sa.String(255), nullable=True),
        sa.Column("routing_key", sa.String(255), nullable=True),
        sa.Column("priority", sa.Integer, nullable=True),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=True),
        # Execution settings
        sa.Column("one_off", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_run_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("date_changed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
    )

    # Create indexes for better performance
    op.create_index("ix_celery_periodic_task_enabled", "celery_periodic_task", ["enabled"])
    op.create_index("ix_celery_periodic_task_interval_id", "celery_periodic_task", ["interval_id"])
    op.create_index("ix_celery_periodic_task_crontab_id", "celery_periodic_task", ["crontab_id"])
    op.create_index("ix_celery_periodic_task_solar_id", "celery_periodic_task", ["solar_id"])


def downgrade() -> None:
    # Drop all Celery Beat tables
    op.drop_index("ix_celery_periodic_task_solar_id", table_name="celery_periodic_task")
    op.drop_index("ix_celery_periodic_task_crontab_id", table_name="celery_periodic_task")
    op.drop_index("ix_celery_periodic_task_interval_id", table_name="celery_periodic_task")
    op.drop_index("ix_celery_periodic_task_enabled", table_name="celery_periodic_task")

    op.drop_table("celery_periodic_task")
    op.drop_table("celery_periodic_task_changed")
    op.drop_table("celery_solar_schedule")
    op.drop_table("celery_crontab_schedule")
    op.drop_table("celery_interval_schedule")

    # Recreate old table (rollback to previous state)
    op.create_table(
        "celery_schedule",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(200), unique=True, nullable=False),
        sa.Column("task", sa.String(200), nullable=False),
        sa.Column("args", sa.dialects.postgresql.JSONB, server_default="[]"),
        sa.Column("kwargs", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_run_count", sa.Integer, server_default="0"),
        sa.Column("date_changed", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
