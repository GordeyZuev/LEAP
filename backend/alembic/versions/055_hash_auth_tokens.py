"""Hash refresh, email-verification, and password-reset tokens at rest

Revision ID: 055
Revises: 054
Create Date: 2026-09-20

Stores SHA-256 hex of refresh JWTs and of email verification / password reset
tokens. Existing plaintext rows are hashed in place. Downgrade cannot restore
plaintext; outstanding reset/verify emails issued before this revision stop
working (users must request a new email).
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa

from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _already_hashed(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _hash_column(conn, table: str, id_column: str, token_column: str) -> None:
    rows = conn.execute(sa.text(f"SELECT {id_column}, {token_column} FROM {table} WHERE {token_column} IS NOT NULL"))
    for row_id, token in rows:
        if not token or _already_hashed(token):
            continue
        conn.execute(
            sa.text(f"UPDATE {table} SET {token_column} = :hashed WHERE {id_column} = :id"),
            {"hashed": _sha256(token), "id": row_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _hash_column(conn, "refresh_tokens", "id", "token")
    _hash_column(conn, "users", "id", "email_verification_token")
    _hash_column(conn, "users", "id", "password_reset_token")


def downgrade() -> None:
    # SHA-256 cannot be reversed; live sessions remain hashed until they expire.
    pass
