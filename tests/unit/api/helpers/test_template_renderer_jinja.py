"""Jinja template renderer: format_datetime_for_template, render, two-step title/description, validation."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.helpers.template_renderer import (
    TemplateRenderer,
    build_stub_validation_context,
    format_datetime_for_template,
    render_jinja,
    render_upload_title_and_description,
    validate_jinja_template,
)


@pytest.mark.unit
class TestFormatDatetimeForTemplate:
    def test_date_keyword(self) -> None:
        dt = datetime(2026, 3, 9, 15, 4, 5, tzinfo=UTC)
        assert format_datetime_for_template(dt, "date") == "2026-03-09"

    def test_dd_mm_yy_tokens(self) -> None:
        dt = datetime(2026, 3, 9, 15, 4, 5, tzinfo=UTC)
        assert format_datetime_for_template(dt, "DD.MM.YY") == "09.03.26"

    def test_non_string_spec_coerced(self) -> None:
        class _Fmt:
            def __str__(self) -> str:
                return "date"

        dt = datetime(2026, 3, 9, 15, 4, 5, tzinfo=UTC)
        assert format_datetime_for_template(dt, _Fmt()) == "2026-03-09"


@pytest.mark.unit
class TestRenderJinja:
    def test_stub_context(self) -> None:
        """Render succeeds with stub validation context."""
        ctx = build_stub_validation_context()
        out = render_jinja("{{ display_name }} — {{ topic }}", ctx)
        assert out == "Stub Recording — stub_topic"

    def test_missing_variable_is_empty(self) -> None:
        """Missing variables stringify to empty (SilentUndefined)."""
        assert render_jinja("x{{ nosuch }}y", {}) == "xy"


@pytest.mark.unit
class TestTwoStepTitleDescription:
    def test_description_sees_rendered_title(self) -> None:
        """Description template can reference rendered title."""
        ctx = build_stub_validation_context()
        title, description = render_upload_title_and_description(
            "{{ display_name }}",
            "Title: {{ title }}",
            ctx,
        )
        assert title == "Stub Recording"
        assert description == "Title: Stub Recording"


@pytest.mark.unit
class TestValidateJinjaTemplate:
    def test_syntax_error_raises_value_error(self) -> None:
        """Broken Jinja raises ValueError with syntax hint."""
        with pytest.raises(ValueError, match="Invalid template syntax"):
            validate_jinja_template("{{ broken", optional=False)


@pytest.mark.unit
class TestFormatTopicsList:
    def test_invalid_start_seconds_omits_timestamp(self) -> None:
        """Non-numeric start does not break the line; timestamp is skipped."""
        out = TemplateRenderer._format_topics_list(
            [{"topic": "Hello", "start": "not-numeric"}],
            {
                "enabled": True,
                "show_timestamps": True,
                "format": "numbered_list",
            },
        )
        assert "Hello" in out
        assert "—" not in out


class TestPrepareRecordingContext:
    def test_original_title_matches_display_name(self) -> None:
        """original_title is set for mapping-style templates (alias of display_name)."""
        rec = SimpleNamespace(
            display_name="Course — Week 1",
            start_time=datetime(2026, 4, 9, 10, 0, 0, tzinfo=UTC),
            duration=3600.0,
            id=7,
            main_topics=None,
            topic_timestamps=None,
            owner=None,
        )
        ctx = TemplateRenderer.prepare_recording_context(rec)
        assert ctx["original_title"] == "Course — Week 1"
        assert ctx["display_name"] == "Course — Week 1"
        assert ctx["record_date_iso"] == "2026-04-09"
        assert isinstance(ctx["record_time"], str)

    def test_zero_duration_preserved(self) -> None:
        """Falsy 0.0 duration must stay numeric for templates and duration_hm."""
        rec = SimpleNamespace(
            display_name="X",
            start_time=datetime(2026, 4, 9, 10, 0, 0, tzinfo=UTC),
            duration=0.0,
            id=1,
            main_topics=None,
            topic_timestamps=None,
            owner=None,
        )
        ctx = TemplateRenderer.prepare_recording_context(rec)
        assert ctx["duration"] == 0.0
        assert ctx["duration_hm"] == "0:00"

    def test_owner_timezone_moscow(self) -> None:
        """Europe/Moscow shifts UTC instant for display strings."""
        owner = SimpleNamespace(timezone="Europe/Moscow", user_slug=1)
        rec = SimpleNamespace(
            display_name="Lecture",
            start_time=datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC),
            duration=1.0,
            id=1,
            main_topics=None,
            topic_timestamps=None,
            owner=owner,
        )
        ctx = TemplateRenderer.prepare_recording_context(rec)
        assert ctx["record_time_hm"] == "15:00"
        assert ctx["record_date_iso"] == "2026-06-15"

    def test_no_start_time_record_timestamp_empty(self) -> None:
        """record_time / record_timestamp_local empty when start_time missing; record_* dates fall back."""
        rec = SimpleNamespace(
            display_name="X",
            start_time=None,
            duration=1.0,
            id=1,
            main_topics=None,
            topic_timestamps=None,
            owner=None,
        )
        ctx = TemplateRenderer.prepare_recording_context(rec)
        assert ctx["record_timestamp_local"] == ""
        assert ctx["publish_timestamp_local"]
        assert len(ctx["record_date_iso"]) == 10 and ctx["record_date_iso"].count("-") == 2
