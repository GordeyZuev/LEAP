"""YouTube snippet.description sanitization for Data API quirks."""

import pytest

from video_upload_module.platforms.youtube.uploader import _sanitize_youtube_description


@pytest.mark.unit
def test_sanitize_replaces_ascii_angle_brackets() -> None:
    assert _sanitize_youtube_description("a > b < c") == "a \uff1e b \uff1c c"


@pytest.mark.unit
def test_sanitize_strips_nul_bytes() -> None:
    assert _sanitize_youtube_description("x\x00y") == "xy"


@pytest.mark.unit
def test_sanitize_empty_unchanged() -> None:
    assert _sanitize_youtube_description("") == ""
