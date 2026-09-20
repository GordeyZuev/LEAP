"""yt-dlp metadata extraction and platform detection."""

import re
from typing import Any
from urllib.parse import urlsplit

from logger import get_logger
from utils.safe_http import YTDLP_HOST_SUFFIXES, host_matches_suffixes, validate_public_url
from video_download_module.platforms.ytdlp.opts import get_ydl_opts

logger = get_logger()


def detect_platform(url: str) -> str:
    """Detect video platform from URL. Returns platform name or 'other'."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return "other"
    platform_hosts = (
        ("youtube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
        ("vk", ("vk.com", "vk.ru", "vkvideo.ru")),
        ("rutube", ("rutube.ru",)),
        ("yandex_disk", ("disk.yandex.ru", "disk.yandex.com", "disk.yandex.net", "yadi.sk")),
    )
    for platform, suffixes in platform_hosts:
        if host_matches_suffixes(host, suffixes):
            return platform
    return "other"


def _raise_friendly(e: Exception) -> None:
    msg = str(e)
    if "rate-limited" in msg or "rate_limit" in msg:
        raise ValueError("YouTube временно ограничил доступ. Попробуйте позже.")
    if "Sign in to confirm" in msg or "not a bot" in msg:
        raise ValueError("YouTube требует авторизацию для этого видео. Попробуйте другое видео.")
    raise ValueError(msg)


async def extract_video_info(url: str) -> dict[str, Any]:
    """Extract video metadata without downloading.

    Returns dict with: id, title, duration, thumbnail, uploader, upload_date, url, platform.
    """
    import asyncio

    import yt_dlp

    url = validate_public_url(url, allowed_host_suffixes=YTDLP_HOST_SUFFIXES)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "noplaylist": True,
        "no_color": True,
    }
    ydl_opts.update(get_ydl_opts())

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.get_event_loop().run_in_executor(None, _extract)
    except yt_dlp.utils.DownloadError:
        await asyncio.sleep(3)
        try:
            info = await asyncio.get_event_loop().run_in_executor(None, _extract)
        except yt_dlp.utils.DownloadError as e:
            _raise_friendly(e)

    if not info:
        raise ValueError(f"Could not extract info from URL: {url}")

    webpage_url = info.get("webpage_url")
    if isinstance(webpage_url, str):
        try:
            webpage_url = validate_public_url(webpage_url, allowed_host_suffixes=YTDLP_HOST_SUFFIXES)
        except ValueError:
            webpage_url = url
    else:
        webpage_url = url

    return {
        "id": info.get("id", ""),
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "url": webpage_url,
        "platform": detect_platform(url),
        "extractor": info.get("extractor_key", ""),
    }


def _parse_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract unique video streams from yt-dlp info_dict, sorted by height desc."""
    raw_formats: list[dict] = info.get("formats") or []
    seen: dict[tuple, dict] = {}
    for f in raw_formats:
        height = f.get("height")
        if not isinstance(height, int) or height <= 0 or f.get("vcodec") == "none":
            continue
        ext = f.get("ext", "")
        key = (height, ext)
        tbr = f.get("tbr") or 0
        if key not in seen or tbr > (seen[key].get("tbr") or 0):
            seen[key] = f
    result = []
    for f in seen.values():
        result.append(
            {
                "height": f.get("height"),
                "ext": f.get("ext", ""),
                "vcodec": f.get("vcodec", ""),
                "fps": f.get("fps"),
                "filesize_approx": f.get("filesize_approx") or f.get("filesize"),
                "format_id": f.get("format_id", ""),
            }
        )
    result.sort(key=lambda x: x["height"] or 0, reverse=True)
    return result


async def extract_available_formats(url: str) -> dict[str, Any]:
    """Fetch video metadata + available video formats without downloading.

    Returns dict with: title, duration, thumbnail, platform, formats list.
    Each format: height, ext, vcodec, fps, filesize_approx, format_id.
    """
    import asyncio

    import yt_dlp

    url = validate_public_url(url, allowed_host_suffixes=YTDLP_HOST_SUFFIXES)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "noplaylist": True,
        "no_color": True,
    }
    ydl_opts.update(get_ydl_opts())

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.get_event_loop().run_in_executor(None, _extract)
    except yt_dlp.utils.DownloadError:
        await asyncio.sleep(3)
        try:
            info = await asyncio.get_event_loop().run_in_executor(None, _extract)
        except yt_dlp.utils.DownloadError as e:
            _raise_friendly(e)

    if not info:
        raise ValueError(f"Could not extract info from URL: {url}")

    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "platform": detect_platform(url),
        "formats": _parse_formats(info),
    }


async def extract_playlist_entries(url: str) -> list[dict[str, Any]]:
    """Extract video entries from a playlist/channel URL (flat, no download).

    Returns list of dicts with: id, title, url, duration, platform.
    """
    import asyncio

    import yt_dlp

    url = validate_public_url(url, allowed_host_suffixes=YTDLP_HOST_SUFFIXES)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "noplaylist": False,
        "ignoreerrors": True,
        "no_color": True,
    }
    ydl_opts.update(get_ydl_opts())

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await asyncio.get_event_loop().run_in_executor(None, _extract)

    if not info:
        raise ValueError(f"Could not extract playlist info from URL: {url}")

    entries = info.get("entries", [])
    if not entries:
        return []

    platform = detect_platform(url)
    result = []
    for entry in entries:
        if entry is None:
            result.append({"unavailable": True})
            continue
        video_url = _playlist_entry_url(entry, platform)
        if not video_url:
            logger.warning("Skipping playlist entry without a video page URL")
            result.append({"unavailable": True})
            continue
        result.append(
            {
                "id": entry.get("id", ""),
                "title": entry.get("title", "Unknown"),
                "url": video_url,
                "duration": entry.get("duration"),
                "platform": platform,
            }
        )

    logger.info(f"Extracted {len(result)} entries from playlist: {url}")
    return result


def _playlist_entry_url(entry: dict[str, Any], platform: str) -> str | None:
    """Flat YouTube entries often contain an ID in `url`, not a page URL."""
    video_id = entry.get("id")
    if platform == "youtube" and isinstance(video_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    for candidate in (entry.get("webpage_url"), entry.get("url")):
        if not isinstance(candidate, str):
            continue
        try:
            parts = urlsplit(candidate)
        except ValueError:
            continue
        if (
            parts.scheme in {"https", "http"}
            and parts.hostname
            and host_matches_suffixes(parts.hostname, YTDLP_HOST_SUFFIXES)
        ):
            return candidate
    return None
