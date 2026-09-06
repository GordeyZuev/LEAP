"""Grant grafana_ro SELECT on share_access_events

Revision ID: 045
Revises: 044
Create Date: 2026-09-06

Overview share panels read calendar-day views/downloads from
``share_access_events``. Default privileges revoke new tables from grafana_ro
(see migration 023), so this grant is explicit.
"""

from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                GRANT SELECT ON share_access_events TO grafana_ro;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                REVOKE SELECT ON share_access_events FROM grafana_ro;
            END IF;
        END
        $$;
        """
    )
