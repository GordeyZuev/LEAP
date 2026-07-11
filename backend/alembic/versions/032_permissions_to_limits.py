"""Drop can_create_templates/can_delete_recordings/can_manage_credentials from users;
add max_templates/max_credentials to subscription_plans and custom_max_* to user_subscriptions

Revision ID: 032
Revises: 031
Create Date: 2026-07-04
"""

import sqlalchemy as sa

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Removed permission flags: deleting own recordings is always allowed; managing
    # credentials and creating templates are now expressed as count-based quota limits.
    op.drop_column("users", "can_create_templates")
    op.drop_column("users", "can_delete_recordings")
    op.drop_column("users", "can_manage_credentials")

    # Count-based limits (NULL = unlimited, 0 = forbidden).
    op.add_column("subscription_plans", sa.Column("max_templates", sa.Integer(), nullable=True))
    op.add_column("subscription_plans", sa.Column("max_credentials", sa.Integer(), nullable=True))
    op.add_column("user_subscriptions", sa.Column("custom_max_templates", sa.Integer(), nullable=True))
    op.add_column("user_subscriptions", sa.Column("custom_max_credentials", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_subscriptions", "custom_max_credentials")
    op.drop_column("user_subscriptions", "custom_max_templates")
    op.drop_column("subscription_plans", "max_credentials")
    op.drop_column("subscription_plans", "max_templates")

    op.add_column(
        "users",
        sa.Column("can_manage_credentials", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("can_delete_recordings", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("can_create_templates", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
