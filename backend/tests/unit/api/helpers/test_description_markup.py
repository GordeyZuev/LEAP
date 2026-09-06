"""Description markup strip and playlist Jinja context."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.helpers.description_markup import markup_to_plain
from api.helpers.playlist_description import build_playlist_description_context, render_playlist_description


@pytest.mark.unit
class TestMarkupToPlain:
    def test_strips_marks_keeps_text(self) -> None:
        src = "**Список тем:** hello **вот такой**"
        assert markup_to_plain(src) == "Список тем: hello вот такой"

    def test_leaves_jinja_untouched(self) -> None:
        src = "**Список тем:** {{ topics }} **вот такой**"
        assert markup_to_plain(src) == "Список тем: {{ topics }} вот такой"

    def test_link_label_and_url(self) -> None:
        assert markup_to_plain("[docs](https://example.com)") == "docs https://example.com"

    def test_bold_not_eaten_as_italic(self) -> None:
        assert markup_to_plain("**bold**") == "bold"

    def test_underline_and_strike(self) -> None:
        assert markup_to_plain("++u++ ~~s~~ *i*") == "u s i"


@pytest.mark.unit
class TestPlaylistDescriptionJinja:
    def test_context_counts_and_items(self) -> None:
        rec_a = SimpleNamespace(display_name="Intro", final_duration=65.0, duration=65.0)
        rec_b = SimpleNamespace(display_name="Joins", final_duration=125.0, duration=125.0)
        playlist = SimpleNamespace(
            items=[
                SimpleNamespace(position=1, recording=rec_a),
                SimpleNamespace(position=0, recording=rec_b),
            ]
        )
        ctx = build_playlist_description_context(playlist)
        assert ctx["video_count"] == 2
        assert ctx["duration_hm"] == "3:10"
        assert ctx["items"] == "1. Joins\n2. Intro"

    def test_render_substitutes(self) -> None:
        rec = SimpleNamespace(display_name="A", final_duration=60.0, duration=60.0)
        playlist = SimpleNamespace(id=1, items=[SimpleNamespace(position=0, recording=rec)])
        out = render_playlist_description("{{ video_count }} | {{ items }}", playlist)
        assert out == "1 | 1. A"
