"""Token version kill-switch + per-session device metadata

Revision ID: 022
Revises: 021
Create Date: 2026-06-01

Adds ``users.token_version`` — an integer epoch embedded into every JWT as
``tv`` claim. Bumping it on logout-all / password change instantly invalidates
all live access tokens for that user (compared against the user row already
fetched in ``get_current_user`` — no extra round-trip).

Adds device metadata columns to ``refresh_tokens`` so the upcoming
"Active sessions" UI can show each session's device label, last activity, and
IP fingerprint without storing raw IP (per CREDENTIAL_SECURITY.md).
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column("refresh_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.String(length=500), nullable=True))
    op.add_column("refresh_tokens", sa.Column("ip_hash", sa.String(length=64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("device_label", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "device_label")
    op.drop_column("refresh_tokens", "ip_hash")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("users", "token_version")
