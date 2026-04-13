"""Migrate legacy `{var}` / `{var:fmt}` metadata templates in JSONB to Jinja2.

Revision ID: 018
Revises: 017
Create Date: 2026-04-09

Strings under known keys are converted: `{name}` → `{{ name }}`,
`{name:fmt}` → `{{ name | leap_dt('fmt') }}`. Rows already containing `{{` or
`{%` are left unchanged. Downgrade is a no-op (irreversible).
"""

from __future__ import annotations

import json
import re
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None

_TEMPLATE_STRING_KEYS: Final[frozenset[str]] = frozenset(
    {
        "title_template",
        "description_template",
        "folder_path_template",
        "filename_template",
        "default_title_template",
    }
)

_LEGACY_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(
    r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([^}]*))?\}",
)


def legacy_brace_template_to_jinja(s: str) -> str:
    """Convert legacy brace placeholders to Jinja (migration-only, not used at runtime)."""

    if not s or "{{" in s or "{%" in s:
        return s

    def _repl(m: re.Match[str]) -> str:
        name = m.group(1)
        fmt = m.group(2)
        if fmt is not None:
            esc = fmt.replace("\\", "\\\\").replace("'", "\\'")
            return f"{{{{ {name} | leap_dt('{esc}') }}}}"
        return f"{{{{ {name} }}}}"

    return _LEGACY_PLACEHOLDER.sub(_repl, s)


def migrate_template_json(obj: Any) -> Any:
    """Recursively migrate template string fields inside JSON-like structures."""

    if isinstance(obj, dict):
        return {
            k: (
                legacy_brace_template_to_jinja(v)
                if k in _TEMPLATE_STRING_KEYS and isinstance(v, str)
                else migrate_template_json(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [migrate_template_json(i) for i in obj]
    return obj


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
        migrated = migrate_template_json(blob)
        if json.dumps(migrated, sort_keys=True, default=str) == json.dumps(blob, sort_keys=True, default=str):
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
    """No-op: legacy strings cannot be reconstructed from Jinja."""
