"""Metadata and format choices used by the Add video dialog."""

from unittest.mock import MagicMock

import pytest

from video_download_module.platforms.ytdlp.downloader import YtDlpDownloader
from video_download_module.platforms.ytdlp.metadata import (
    _parse_formats,
    detect_platform,
    extract_playlist_entries,
    extract_video_info,
)


@pytest.mark.unit
def test_platform_detection_uses_hostname_not_query_text():
    assert detect_platform("https://vimeo.com/123?next=youtube.com") == "other"
    assert detect_platform("https://www.youtube.com/watch?v=123&next=vk.com") == "youtube"
    assert detect_platform("https://fake-youtube.com/watch?v=123") == "other"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_video_metadata_keeps_allowed_url_when_extractor_returns_external_page(mocker):
    def validate(url, **_kwargs):
        if "external.example" in url:
            raise ValueError("Host is not on the allowlist")
        return url

    mocker.patch("video_download_module.platforms.ytdlp.metadata.validate_public_url", side_effect=validate)
    mocker.patch("video_download_module.platforms.ytdlp.metadata.get_ydl_opts", return_value={})
    ydl = mocker.patch("yt_dlp.YoutubeDL")
    ydl.return_value.__enter__.return_value.extract_info.return_value = {
        "id": "abcdefghijk",
        "title": "Lecture",
        "webpage_url": "https://external.example/video",
    }

    info = await extract_video_info("https://www.youtube.com/watch?v=abcdefghijk")

    assert info["url"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert info["platform"] == "youtube"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_youtube_playlist_flat_ids_become_video_page_urls(mocker):
    mocker.patch("video_download_module.platforms.ytdlp.metadata.validate_public_url", side_effect=lambda url, **_: url)
    mocker.patch("video_download_module.platforms.ytdlp.metadata.get_ydl_opts", return_value={})
    ydl = mocker.patch("yt_dlp.YoutubeDL")
    ydl.return_value.__enter__.return_value.extract_info.return_value = {
        "_type": "playlist",
        "entries": [
            {"id": "abcdefghijk", "url": "abcdefghijk", "title": "Lecture"},
            None,
            {"id": "lmnopqrstuv", "webpage_url": "https://www.youtube.com/watch?v=lmnopqrstuv"},
        ],
    }

    entries = await extract_playlist_entries("https://www.youtube.com/playlist?list=PL123")

    assert [entry["url"] for entry in entries if not entry.get("unavailable")] == [
        "https://www.youtube.com/watch?v=abcdefghijk",
        "https://www.youtube.com/watch?v=lmnopqrstuv",
    ]
    assert sum(bool(entry.get("unavailable")) for entry in entries) == 1
    assert ydl.call_args.args[0]["noplaylist"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_playlist_import_does_not_treat_single_video_as_playlist(mocker):
    mocker.patch("video_download_module.platforms.ytdlp.metadata.validate_public_url", side_effect=lambda url, **_: url)
    mocker.patch("video_download_module.platforms.ytdlp.metadata.get_ydl_opts", return_value={})
    ydl = mocker.patch("yt_dlp.YoutubeDL")
    ydl.return_value.__enter__.return_value.extract_info.return_value = {
        "id": "abcdefghijk",
        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
    }

    assert await extract_playlist_entries("https://www.youtube.com/watch?v=abcdefghijk") == []


@pytest.mark.unit
def test_preview_excludes_audio_only_formats():
    formats = _parse_formats(
        {
            "formats": [
                {"height": 1080, "ext": "mp4", "vcodec": "avc1", "tbr": 1200},
                {"height": 1080, "ext": "mp4", "vcodec": "avc1", "tbr": 1800},
                {"height": 720, "ext": "m4a", "vcodec": "none", "tbr": 200},
            ]
        }
    )

    assert [(item["height"], item["ext"]) for item in formats] == [(1080, "mp4")]
    assert formats[0]["format_id"] == ""


@pytest.mark.unit
@pytest.mark.parametrize("quality,height", [("1440p", 1440), ("1080p", 1080), ("720p", 720), ("480p", 480)])
def test_quality_limit_applies_to_every_download_fallback(quality, height):
    spec = YtDlpDownloader(user_slug=1)._build_format_spec(quality, "mp4")

    assert spec.split("/")
    assert all(f"height<={height}" in branch for branch in spec.split("/"))
    assert YtDlpDownloader(user_slug=1)._build_ydl_opts(MagicMock(), spec, "mp4")["merge_output_format"] == "mp4/mkv"
