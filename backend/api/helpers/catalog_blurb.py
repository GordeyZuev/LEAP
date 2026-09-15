"""Short public-catalog blurbs (list view), not full share Overview payloads."""

from __future__ import annotations

from typing import Any

CATALOG_BLURB_MAX = 280


def excerpt(text: str | None, *, max_len: int = CATALOG_BLURB_MAX) -> str | None:
    """Collapse whitespace and cap length for a two-line catalog snippet."""
    if text is None:
        return None
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    if len(collapsed) <= max_len:
        return collapsed
    cut = collapsed[:max_len].rsplit(" ", 1)[0].rstrip(".,;:—-–")
    if not cut:
        cut = collapsed[:max_len]
    return f"{cut}…"


def recording_catalog_blurb(recording: Any) -> str | None:
    """DB-only teaser: main_topics already on the recording row (no extracted.json)."""
    topics = getattr(recording, "main_topics", None)
    if not isinstance(topics, list):
        return None
    parts: list[str] = []
    for item in topics:
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("topic") or item.get("title") or item.get("name")
            if isinstance(label, str) and label.strip():
                parts.append(label.strip())
    if not parts:
        return None
    return excerpt(" · ".join(parts))
