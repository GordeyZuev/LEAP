"""Add affected_recordings snapshot to automation_job_runs

Revision ID: 047
Revises: 046
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("automation_job_runs", sa.Column("affected_recordings", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("automation_job_runs", "affected_recordings")
