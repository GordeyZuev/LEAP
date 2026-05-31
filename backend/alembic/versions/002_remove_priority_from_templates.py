"""Remove priority field from recording_templates

Revision ID: 002
Revises: 001
Create Date: 2026-01-22

"""

from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove priority column from recording_templates if it exists.

    Historically `priority` was created here and dropped later, but 001 was
    refactored to never create it. On a clean DB the column never exists;
    on a legacy DB it does. Guard with an inspector so both paths succeed.
    """
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("recording_templates")}
    if "priority" in columns:
        op.drop_column("recording_templates", "priority")


def downgrade() -> None:
    """Restore priority column to recording_templates table."""
    import sqlalchemy as sa

    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("recording_templates")}
    if "priority" not in columns:
        op.add_column(
            "recording_templates", sa.Column("priority", sa.Integer, default=0, nullable=False, server_default="0")
        )
