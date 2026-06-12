"""Grant grafana_ro SELECT on stage_timings for pipeline dashboards

Revision ID: 025
Revises: 024
Create Date: 2026-06-12

Pipeline stage duration / failure panels read from the append-only
``stage_timings`` table (see migration 014). Celery workers emit Prometheus
histograms that are not scraped today; Postgres is the authoritative source.
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                GRANT SELECT ON stage_timings TO grafana_ro;
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
                REVOKE SELECT ON stage_timings FROM grafana_ro;
            END IF;
        END
        $$;
        """
    )
