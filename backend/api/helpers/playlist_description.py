"""Jinja context for playlist descriptions: video_count, duration_hm, items."""

from __future__ import annotations

from typing import Any

from api.helpers.media_duration import display_duration_seconds
from api.helpers.template_renderer import TemplateRenderer, render_jinja
from logger import get_logger

logger = get_logger(__name__)


def description_needs_item_titles(raw: str | None) -> bool:
    if not raw:
        return False
    return "items" in raw


def build_playlist_description_context(
    playlist: Any | None = None,
    *,
    item_titles: dict[int, str] | None = None,
    video_count: int | None = None,
    duration_sum: float | None = None,
    ordered_titles: list[str] | None = None,
) -> dict[str, Any]:
    if ordered_titles is not None:
        titles = ordered_titles
        count = video_count if video_count is not None else len(titles)
        duration = float(duration_sum or 0)
    else:
        rows = sorted(getattr(playlist, "items", None) or [], key=lambda i: i.position)
        titles = []
        duration = 0.0
        for item in rows:
            rec = getattr(item, "recording", None)
            if rec is not None and item_titles and rec.id in item_titles:
                titles.append(item_titles[rec.id])
            else:
                titles.append(rec.display_name if rec is not None else "Unknown")
            if rec is not None:
                duration += display_duration_seconds(rec)
        count = video_count if video_count is not None else len(rows)
        if duration_sum is not None:
            duration = float(duration_sum)
    items_block = "\n".join(f"{i}. {title}" for i, title in enumerate(titles, start=1))
    return {
        "video_count": count,
        "duration_hm": TemplateRenderer._duration_hm_str(duration),
        "items": items_block,
    }


def render_playlist_description(
    raw: str | None,
    playlist: Any | None = None,
    *,
    item_titles: dict[int, str] | None = None,
    video_count: int | None = None,
    duration_sum: float | None = None,
    ordered_titles: list[str] | None = None,
) -> str | None:
    """Render playlist description Jinja. Markup is left for the client. None if empty."""
    if raw is None or not raw.strip():
        return None
    try:
        rendered = render_jinja(
            raw,
            build_playlist_description_context(
                playlist,
                item_titles=item_titles,
                video_count=video_count,
                duration_sum=duration_sum,
                ordered_titles=ordered_titles,
            ),
        )
    except Exception:
        logger.debug("Playlist description Jinja failed | playlist={}", getattr(playlist, "id", None))
        rendered = raw
    return rendered if rendered.strip() else None
