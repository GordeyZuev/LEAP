"""Unit tests for leap_dt → canonical variable string migration (019)."""

from __future__ import annotations

import pytest

from api.helpers.leap_dt_template_migration import (
    json_equal,
    migrate_json_template_strings,
    replace_leap_dt_in_string,
)


@pytest.mark.unit
class TestReplaceLeapDtInString:
    def test_record_dd_mm_yy(self) -> None:
        s = "{{ record_time | leap_dt('DD.MM.YY') }}"
        out, r, u = replace_leap_dt_in_string(s)
        assert out == "{{ record_date_short }}"
        assert r == 1 and u == 0

    def test_publish_date_keyword(self) -> None:
        s = "{{ publish_time | leap_dt('date') }}"
        out, r, u = replace_leap_dt_in_string(s)
        assert out == "{{ publish_date_iso }}"
        assert r == 1 and u == 0

    def test_tight_spacing_and_double_quotes(self) -> None:
        s = '{{record_time|leap_dt("date")}}'
        out, r, u = replace_leap_dt_in_string(s)
        assert out == "{{ record_date_iso }}"
        assert r == 1 and u == 0

    def test_idempotent(self) -> None:
        s = "{{ record_date_iso }}"
        out, r, u = replace_leap_dt_in_string(s)
        assert out == s and r == 0 and u == 0

    def test_unknown_fmt_left_and_unmapped(self) -> None:
        s = "{{ record_time | leap_dt('MM/DD/YYYY') }}"
        out, r, u = replace_leap_dt_in_string(s)
        assert out == s
        assert r == 0 and u == 1

    def test_other_variable_untouched(self) -> None:
        s = "{{ foo | leap_dt('date') }}"
        out, r, u = replace_leap_dt_in_string(s)
        assert out == s
        assert r == 0 and u == 0


@pytest.mark.unit
class TestMigrateJsonTemplateStrings:
    def test_nested_metadata(self) -> None:
        blob = {
            "title_template": "{{ record_time | leap_dt('DD.MM.YYYY') }}",
            "vk": {"description_template": "{{ publish_time | leap_dt('datetime') }}"},
        }
        migrated, r, u = migrate_json_template_strings(blob)
        assert migrated["title_template"] == "{{ record_date }}"
        assert migrated["vk"]["description_template"] == "{{ publish_datetime_iso }}"
        assert r == 2 and u == 0

    def test_json_equal_idempotent_second_pass(self) -> None:
        blob = {"t": "{{ record_time | leap_dt('date') }}"}
        once, _, _ = migrate_json_template_strings(blob)
        twice, r2, _ = migrate_json_template_strings(once)
        assert json_equal(once, twice)
        assert r2 == 0
