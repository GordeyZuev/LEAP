"""Replace ``| leap_dt(...)`` in template JSONB with canonical Jinja variables.

Revision ID: 019
Revises: 018
Create Date: 2026-04-09

Downgrade is a no-op (irreversible).
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op
from api.helpers.leap_dt_template_migration import json_equal, migrate_json_template_strings

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def _migrate_rows(
    conn: sa.Connection,
    *,
    select_sql: str,
    update_sql: str,
) -> None:
    rows = conn.execute(text(select_sql)).fetchall()

    for pk, blob in rows:
        if blob is None:
            continue
        migrated, _r, _u = migrate_json_template_strings(blob)
        if json_equal(migrated, blob):
            continue
        conn.execute(
            text(update_sql),
            {"payload": json.dumps(migrated), "pk": pk},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _migrate_rows(
        conn,
        select_sql="SELECT id, metadata_config FROM recording_templates WHERE metadata_config IS NOT NULL",
        update_sql="UPDATE recording_templates SET metadata_config = CAST(:payload AS jsonb) WHERE id = :pk",
    )
    _migrate_rows(
        conn,
        select_sql="SELECT id, preset_metadata FROM output_presets WHERE preset_metadata IS NOT NULL",
        update_sql="UPDATE output_presets SET preset_metadata = CAST(:payload AS jsonb) WHERE id = :pk",
    )
    _migrate_rows(
        conn,
        select_sql="SELECT id, processing_preferences FROM recordings WHERE processing_preferences IS NOT NULL",
        update_sql="UPDATE recordings SET processing_preferences = CAST(:payload AS jsonb) WHERE id = :pk",
    )
    _migrate_rows(
        conn,
        select_sql="SELECT id, config_data FROM user_configs WHERE config_data IS NOT NULL",
        update_sql="UPDATE user_configs SET config_data = CAST(:payload AS jsonb) WHERE id = :pk",
    )


def downgrade() -> None:
    """No-op: leap_dt call sites cannot be reconstructed from canonical names."""
