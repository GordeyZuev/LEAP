"""Publication title fallbacks (leap look, then global template, then display_name)."""

from types import SimpleNamespace

import pytest

from api.helpers.leap_publication import _as_int_ids, _leap_look_meta, render_publication_title


@pytest.mark.unit
def test_title_prefers_leap_then_global_then_display() -> None:
    rec = SimpleNamespace(id=1, display_name="Source")
    assert (
        render_publication_title(
            rec,
            leap_meta={"title_template": "{{ display_name }} · published"},
            global_title_template="{{ display_name }} · global",
        )
        == "Source · published"
    )
    assert (
        render_publication_title(rec, leap_meta=None, global_title_template="{{ display_name }} · global")
        == "Source · global"
    )
    assert render_publication_title(rec, leap_meta=None, global_title_template=None) == "Source"


@pytest.mark.unit
def test_blank_jinja_falls_back_to_display_name() -> None:
    rec = SimpleNamespace(id=1, display_name="Source")
    assert render_publication_title(rec, leap_meta={"title_template": "   "}, global_title_template=None) == "Source"


@pytest.mark.unit
def test_template_leap_override_wins_over_preset() -> None:
    rec = SimpleNamespace(id=1, display_name="Source")
    merged = {
        "title_template": "{{ display_name }} · override",
        "description_template": "from preset",
    }
    assert (
        render_publication_title(
            rec,
            leap_meta=merged,
            global_title_template="{{ display_name }} · global",
        )
        == "Source · override"
    )


@pytest.mark.unit
def test_as_int_ids_coerces_digit_strings() -> None:
    assert _as_int_ids([1, "2", True, 0, "x", None]) == [1, 2]


@pytest.mark.unit
def test_leap_look_meta_requires_active_preset() -> None:
    overlay = {"title_template": "{{ display_name }} · leftover"}
    assert _leap_look_meta(None, overlay) is None

    leap = SimpleNamespace(preset_metadata={"title_template": "{{ display_name }} · look"})
    merged = _leap_look_meta(leap, overlay)
    assert merged is not None
    assert merged["title_template"] == "{{ display_name }} · leftover"
