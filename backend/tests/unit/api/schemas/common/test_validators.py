"""Tests for shared string validators."""

import pytest

from api.helpers.text import collapse_whitespace
from api.schemas.common.validators import clean_and_deduplicate_strings
from api.schemas.recording.request import RecordingUpdateRequest
from api.schemas.template.matching_rules import MatchingRules


@pytest.mark.unit
def test_collapse_whitespace_newlines_and_tabs() -> None:
    raw = "ИИ_1 курс_Инструменты разработки\n1 группа  2026-09-08\t18:09:11"
    assert collapse_whitespace(raw) == "ИИ_1 курс_Инструменты разработки 1 группа 2026-09-08 18:09:11"


@pytest.mark.unit
def test_clean_and_deduplicate_collapses_exact_matches() -> None:
    cleaned = clean_and_deduplicate_strings(["foo\nbar", "foo bar"])
    assert cleaned == ["foo bar"]


@pytest.mark.unit
def test_matching_rules_collapse_exact_matches() -> None:
    rules = MatchingRules.model_validate({"exact_matches": ["Lecture\n1"]})
    assert rules.exact_matches == ["Lecture 1"]


@pytest.mark.unit
def test_recording_update_collapses_display_name() -> None:
    body = RecordingUpdateRequest.model_validate({"display_name": "A\nB"})
    assert body.display_name == "A B"
