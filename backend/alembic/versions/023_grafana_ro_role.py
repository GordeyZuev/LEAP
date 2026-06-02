"""Grafana read-only role for dashboards

Revision ID: 023
Revises: 022
Create Date: 2026-06-02

Creates the ``grafana_ro`` Postgres role used by the LEAP Overview dashboard's
LEAP-DB datasource. Password comes from ``GRAFANA_RO_PASSWORD`` — same env
Grafana itself reads, so both sides stay in sync. When the env is unset the
role is not provisioned (migration still marks itself applied); re-run
``alembic downgrade 022 && alembic upgrade head`` after the secret is in place.
"""

import os

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


READABLE_TABLES = (
    "users",
    "recordings",
    "output_targets",
    "user_subscriptions",
    "subscription_plans",
    "quota_usage",
    "user_credentials",
)


def upgrade() -> None:
    password = os.environ.get("GRAFANA_RO_PASSWORD") or ""
    if not password:
        print("[migration 023] GRAFANA_RO_PASSWORD not set — skipping grafana_ro role.")
        return

    escaped = password.replace("'", "''")

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                EXECUTE format('CREATE ROLE grafana_ro NOINHERIT LOGIN PASSWORD %L', '{escaped}');
            END IF;
        END
        $$;
        """
    )

    op.execute("GRANT CONNECT ON DATABASE leap_platform TO grafana_ro;")
    op.execute("GRANT USAGE ON SCHEMA public TO grafana_ro;")
    for table in READABLE_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO grafana_ro;")

    # Newly-created tables in `public` are NOT auto-granted; we want explicit grants only.
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM grafana_ro;")


def downgrade() -> None:
    for table in READABLE_TABLES:
        op.execute(f"REVOKE SELECT ON {table} FROM grafana_ro;")
    op.execute("REVOKE USAGE ON SCHEMA public FROM grafana_ro;")
    op.execute("REVOKE CONNECT ON DATABASE leap_platform FROM grafana_ro;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                DROP ROLE grafana_ro;
            END IF;
        END
        $$;
        """
    )
