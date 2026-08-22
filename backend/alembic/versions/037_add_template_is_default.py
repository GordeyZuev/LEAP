"""Add is_default flag to recording_templates

Revision ID: 037
Revises: 036
Create Date: 2026-08-22
"""

import sqlalchemy as sa

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recording_templates",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_templates_user_default",
        "recording_templates",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )
    op.alter_column("recording_templates", "is_default", server_default=None)


def downgrade() -> None:
    op.drop_index("uq_templates_user_default", table_name="recording_templates")
    op.drop_column("recording_templates", "is_default")
