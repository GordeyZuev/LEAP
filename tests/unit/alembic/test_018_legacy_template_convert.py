"""Tests for Alembic 018 legacy `{var}` → Jinja conversion helpers (migration-only)."""

import importlib.util
from pathlib import Path

import pytest


def _load_018_module():
    root = Path(__file__).resolve().parents[3]
    path = root / "alembic" / "versions" / "018_jinja_metadata_templates_data_migration.py"
    spec = importlib.util.spec_from_file_location("rev018_jinja_metadata", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
class TestLegacyBraceToJinja:
    def test_simple_placeholder(self) -> None:
        """Single-brace placeholder becomes Jinja variable."""
        m = _load_018_module()
        assert m.legacy_brace_template_to_jinja("{display_name}") == "{{ display_name }}"

    def test_with_format_uses_leap_dt(self) -> None:
        """Formatted legacy placeholder uses leap_dt filter."""
        m = _load_018_module()
        out = m.legacy_brace_template_to_jinja("{record_time:DD.MM.YY}")
        assert out == "{{ record_time | leap_dt('DD.MM.YY') }}"

    def test_already_jinja_unchanged(self) -> None:
        """Strings that already use Jinja delimiters are not modified."""
        m = _load_018_module()
        s = "{{ display_name }} | {{ themes }}"
        assert m.legacy_brace_template_to_jinja(s) is s

    def test_migrate_nested_json(self) -> None:
        """Recursive JSON walk updates known template keys only."""
        m = _load_018_module()
        data = {
            "title_template": "{themes}",
            "vk": {"title_template": "{record_time:date}", "album_id": "1"},
        }
        out = m.migrate_template_json(data)
        assert out["title_template"] == "{{ themes }}"
        assert out["vk"]["title_template"] == "{{ record_time | leap_dt('date') }}"
        assert out["vk"]["album_id"] == "1"
