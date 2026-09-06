"""Jinja context for playlist descriptions: video_count, duration_hm, items."""

from __future__ import annotations

from typing import Any

from api.helpers.template_renderer import TemplateRenderer, render_jinja
from logger import get_logger

logger = get_logger(__name__)


def build_playlist_description_context(playlist: Any) -> dict[str, Any]:
    rows = sorted(playlist.items or [], key=lambda i: i.position)
    titles: list[str] = []
    duration = 0.0
    for item in rows:
        rec = getattr(item, "recording", None)
        titles.append(rec.display_name if rec is not None else "Unknown")
        if rec is not None:
            duration += rec.final_duration or rec.duration or 0.0
    items_block = "\n".join(f"{i}. {title}" for i, title in enumerate(titles, start=1))
    return {
        "video_count": len(rows),
        "duration_hm": TemplateRenderer._duration_hm_str(duration),
        "items": items_block,
    }


def render_playlist_description(raw: str | None, playlist: Any) -> str | None:
    """Render playlist description Jinja. Markup is left for the client. None if empty."""
    if raw is None or not raw.strip():
        return None
    try:
        rendered = render_jinja(raw, build_playlist_description_context(playlist))
    except Exception:
        logger.debug("Playlist description Jinja failed | playlist={}", getattr(playlist, "id", None))
        rendered = raw
    return rendered if rendered.strip() else None
