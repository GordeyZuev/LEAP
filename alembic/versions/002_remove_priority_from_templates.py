"""Remove priority field from recording_templates

Revision ID: 002
Revises: 001
Create Date: 2026-01-22

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove priority column from recording_templates table."""
    # Drop priority column if it exists
    op.drop_column("recording_templates", "priority")


def downgrade() -> None:
    """Restore priority column to recording_templates table."""
    import sqlalchemy as sa

    op.add_column(
        "recording_templates",
        sa.Column("priority", sa.Integer, default=0, nullable=False, server_default="0")
    )
