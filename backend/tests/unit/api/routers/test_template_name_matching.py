"""Template matching uses collapsed whitespace on display names."""

from types import SimpleNamespace

import pytest

from api.routers.input_sources import _find_matching_template


@pytest.mark.unit
def test_exact_match_ignores_newlines_in_display_name() -> None:
    template = SimpleNamespace(
        id=1,
        matching_rules={
            "exact_matches": ["ИИ_1 курс_Инструменты разработки 1 группа 2026-09-08 18:09:11"],
            "case_sensitive": False,
        },
    )
    display_name = "ИИ_1 курс_Инструменты разработки\n1 группа 2026-09-08 18:09:11"
    matched = _find_matching_template(display_name, source_id=1, templates=[template])
    assert matched is template


@pytest.mark.unit
def test_keyword_match_space_vs_newline() -> None:
    template = SimpleNamespace(
        id=2,
        matching_rules={"keywords": ["разработки 1 группа"], "case_sensitive": False},
    )
    display_name = "ИИ_1 курс_Инструменты разработки\n1 группа"
    matched = _find_matching_template(display_name, source_id=1, templates=[template])
    assert matched is template


@pytest.mark.unit
def test_regex_match_uses_collapsed_display_name() -> None:
    template = SimpleNamespace(
        id=3,
        matching_rules={"patterns": ["разработки 1 группа"], "case_sensitive": False},
    )
    display_name = "ИИ_1 курс_Инструменты разработки\n1 группа"
    matched = _find_matching_template(display_name, source_id=1, templates=[template])
    assert matched is template
