"""Jinja context for channel descriptions: video_count, playlist_count, duration_hm, items, playlists."""

from __future__ import annotations

from typing import Any

from api.helpers.template_renderer import TemplateRenderer, render_jinja
from logger import get_logger

logger = get_logger(__name__)


def build_channel_description_context(
    *,
    video_count: int = 0,
    playlist_count: int = 0,
    duration_sum: float = 0,
    video_titles: list[str] | None = None,
    playlist_names: list[str] | None = None,
) -> dict[str, Any]:
    titles = video_titles or []
    names = playlist_names or []
    return {
        "video_count": video_count,
        "playlist_count": playlist_count,
        "duration_hm": TemplateRenderer._duration_hm_str(duration_sum),
        "items": "\n".join(f"{i}. {title}" for i, title in enumerate(titles, start=1)),
        "playlists": "\n".join(f"{i}. {name}" for i, name in enumerate(names, start=1)),
    }


def render_channel_description(
    raw: str | None,
    *,
    video_count: int = 0,
    playlist_count: int = 0,
    duration_sum: float = 0,
    video_titles: list[str] | None = None,
    playlist_names: list[str] | None = None,
) -> str | None:
    """Render channel description Jinja. Markup is left for the client. None if empty."""
    if raw is None or not raw.strip():
        return None
    try:
        rendered = render_jinja(
            raw,
            build_channel_description_context(
                video_count=video_count,
                playlist_count=playlist_count,
                duration_sum=duration_sum,
                video_titles=video_titles,
                playlist_names=playlist_names,
            ),
        )
    except Exception:
        logger.debug("Channel description Jinja failed")
        rendered = raw
    return rendered if rendered.strip() else None
