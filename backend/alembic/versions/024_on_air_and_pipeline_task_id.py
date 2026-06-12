"""Pipeline activity flag and task tracking

Revision ID: 024
Revises: 023
Create Date: 2026-06-12

Adds two columns to ``recordings``:

- ``on_air`` — boolean, True while a Celery pipeline chain is actively
  executing for this recording. Acts as the single guard against duplicate
  pipeline launches and is the canonical "is something running?" signal for
  the UI. Cleared on success, failure, and hard pause.

- ``pipeline_task_id`` — VARCHAR storing the Celery chain ID dispatched for
  this recording. Used to revoke the chain on pause and for maintenance
  detection of stuck pipelines.
"""

import sqlalchemy as sa

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("on_air", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "recordings",
        sa.Column("pipeline_task_id", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_recordings_on_air", "recordings", ["on_air"])


def downgrade() -> None:
    op.drop_index("ix_recordings_on_air", table_name="recordings")
    op.drop_column("recordings", "pipeline_task_id")
    op.drop_column("recordings", "on_air")
