"""Unit tests for topics_display / questions_display normalization in preset_metadata."""

import pytest

from api.schemas.template.preset_metadata import (
    display_config_defaults_payload,
    normalize_questions_display,
    normalize_topics_display,
)


@pytest.mark.unit
class TestNormalizeTopicsDisplay:
    def test_none_uses_effective_defaults(self) -> None:
        cfg = normalize_topics_display(None)
        assert cfg["max_count"] == 999
        assert cfg["min_length"] == 0
        assert cfg["max_length"] == 999
        assert cfg["show_timestamps"] is False

    def test_null_max_count_keeps_effective_default(self) -> None:
        cfg = normalize_topics_display({"max_count": None, "enabled": True})
        assert cfg["max_count"] == 999

    def test_explicit_max_count_overrides(self) -> None:
        cfg = normalize_topics_display({"max_count": 10})
        assert cfg["max_count"] == 10


@pytest.mark.unit
class TestNormalizeQuestionsDisplay:
    def test_none_uses_effective_defaults(self) -> None:
        cfg = normalize_questions_display(None)
        assert cfg["max_count"] == 20
        assert cfg["max_length"] == 1000

    def test_null_max_count_keeps_effective_default(self) -> None:
        cfg = normalize_questions_display({"max_count": None})
        assert cfg["max_count"] == 20


@pytest.mark.unit
class TestDisplayConfigDefaultsPayload:
    def test_payload_matches_normalize(self) -> None:
        payload = display_config_defaults_payload()
        assert payload["topics"] == normalize_topics_display(None)
        assert payload["questions"] == normalize_questions_display(None)
        assert payload["bounds"]["topics"]["max_count"]["max"] == 999
        assert payload["bounds"]["questions"]["max_count"]["max"] == 20
