"""Public catalog blurb excerpts."""

from __future__ import annotations

import pytest

from api.helpers.catalog_blurb import excerpt, recording_catalog_blurb
from tests.fixtures.factories import create_mock_recording


@pytest.mark.unit
class TestExcerpt:
    def test_empty(self) -> None:
        assert excerpt(None) is None
        assert excerpt("  \n  ") is None

    def test_collapses_whitespace(self) -> None:
        assert excerpt("  Hello\n\nworld  ") == "Hello world"

    def test_truncates_on_word(self) -> None:
        text = "alpha " * 80
        got = excerpt(text, max_len=40)
        assert got is not None
        assert got.endswith("…")
        assert len(got) <= 41
        assert "alpha" in got


@pytest.mark.unit
class TestRecordingCatalogBlurb:
    def test_joins_main_topics(self) -> None:
        rec = create_mock_recording(record_id=11, main_topics=[" Joins ", "Indexes"])
        assert recording_catalog_blurb(rec) == "Joins · Indexes"

    def test_dict_topics(self) -> None:
        rec = create_mock_recording(record_id=11, main_topics=[{"topic": "Windows"}])
        assert recording_catalog_blurb(rec) == "Windows"

    def test_missing(self) -> None:
        rec = create_mock_recording(record_id=11, main_topics=None)
        assert recording_catalog_blurb(rec) is None
