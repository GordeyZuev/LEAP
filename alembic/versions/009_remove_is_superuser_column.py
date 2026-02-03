"""remove_is_superuser_column

Revision ID: 009
Revises: 008
Create Date: 2026-02-03

Removes is_superuser column from users table as we use role-based access control.
"""

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "is_superuser")


def downgrade() -> None:
    op.add_column("users", sa.Column("is_superuser", sa.Boolean, default=False, nullable=False))
