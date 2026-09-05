"""Tests for recording poster thumbnail resolution."""

from api.services.config_resolver import extract_thumbnail_name_from_metadata


def test_extract_thumbnail_name_prefers_common_over_platform():
    metadata = {
        "thumbnail_name": "common.png",
        "youtube": {"thumbnail_name": "yt.png"},
    }
    assert extract_thumbnail_name_from_metadata(metadata) == "common.png"


def test_extract_thumbnail_name_falls_back_to_common():
    metadata = {"thumbnail_name": "common.png"}
    assert extract_thumbnail_name_from_metadata(metadata) == "common.png"


def test_extract_thumbnail_name_falls_back_to_platform():
    metadata = {
        "youtube": {"thumbnail_name": "yt.png"},
        "vk": {"thumbnail_name": "vk.png"},
    }
    assert extract_thumbnail_name_from_metadata(metadata) == "yt.png"


def test_extract_thumbnail_name_ignores_blank():
    assert extract_thumbnail_name_from_metadata({"thumbnail_name": "  "}) is None
    assert extract_thumbnail_name_from_metadata({}) is None
