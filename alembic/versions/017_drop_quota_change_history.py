"""Drop quota_change_history table

Revision ID: 017
Revises: 016
Create Date: 2026-02-16

Table is unused and not needed for current scope.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("quota_change_history")


def downgrade() -> None:
    op.create_table(
        "quota_change_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("changed_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_type", sa.String(50), nullable=False, index=True),
        sa.Column(
            "old_plan_id", sa.Integer(), sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "new_plan_id", sa.Integer(), sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("changes", JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
