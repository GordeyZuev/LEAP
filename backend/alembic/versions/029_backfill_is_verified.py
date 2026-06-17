"""Backfill is_verified=true for all existing users

Revision ID: 029
Revises: 028
Create Date: 2026-06-17

is_verified has existed since revision 001 but was never enforced.
Login now rejects unverified users (email-verification flow added in this
release), so every pre-existing account must be marked verified to avoid
locking out active users on upgrade.

New registrations after this release go through email verification normally.
"""

import sqlalchemy as sa

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET is_verified = true WHERE is_verified = false"))


def downgrade() -> None:
    # Intentionally a no-op: we cannot know which users were unverified before.
    pass
