"""yt-dlp metadata extraction and platform detection."""

import re
from typing import Any

from logger import get_logger

logger = get_logger()

# Platform detection patterns
_PLATFORM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("youtube", re.compile(r"(?:youtube\.com|youtu\.be)", re.IGNORECASE)),
    ("vk", re.compile(r"(?:vk\.com|vkvideo\.ru)", re.IGNORECASE)),
    ("rutube", re.compile(r"rutube\.ru", re.IGNORECASE)),
    ("yandex_disk", re.compile(r"(?:disk\.yandex\.|yadi\.sk)", re.IGNORECASE)),
]


def detect_platform(url: str) -> str:
    """Detect video platform from URL. Returns platform name or 'other'."""
    for platform, pattern in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return platform
    return "other"


async def extract_video_info(url: str) -> dict[str, Any]:
    """Extract video metadata without downloading.

    Returns dict with: id, title, duration, thumbnail, uploader, upload_date, url, platform.
    """
    import asyncio

    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "no_color": True,
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await asyncio.get_event_loop().run_in_executor(None, _extract)

    if not info:
        raise ValueError(f"Could not extract info from URL: {url}")

    return {
        "id": info.get("id", ""),
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "url": info.get("webpage_url", url),
        "platform": detect_platform(url),
        "extractor": info.get("extractor_key", ""),
    }


async def extract_playlist_entries(url: str) -> list[dict[str, Any]]:
    """Extract video entries from a playlist/channel URL (flat, no download).

    Returns list of dicts with: id, title, url, duration, platform.
    """
    import asyncio

    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "no_color": True,
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await asyncio.get_event_loop().run_in_executor(None, _extract)

    if not info:
        raise ValueError(f"Could not extract playlist info from URL: {url}")

    entries = info.get("entries", [])
    if not entries:
        # Single video, not a playlist
        return [
            {
                "id": info.get("id", ""),
                "title": info.get("title", "Unknown"),
                "url": info.get("webpage_url", url),
                "duration": info.get("duration"),
                "platform": detect_platform(url),
            }
        ]

    platform = detect_platform(url)
    result = []
    for entry in entries:
        if entry is None:
            continue
        result.append(
            {
                "id": entry.get("id", ""),
                "title": entry.get("title", "Unknown"),
                "url": entry.get("url") or entry.get("webpage_url", ""),
                "duration": entry.get("duration"),
                "platform": platform,
            }
        )

    logger.info(f"Extracted {len(result)} entries from playlist: {url}")
    return result
