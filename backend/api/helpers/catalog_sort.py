"""Saved sort rules for playlist items and channel members.

Owners pick a rule once; it is stored and re-applied whenever members are added, so new videos land in
place. Only rules whose order cannot drift without an add are offered (no views, counts, or durations).
Keep keys in line with the owner catalogs in ``frontend/src/lib/playlist-catalog.ts`` and
``frontend/src/lib/channel-catalog.ts``.
"""

from __future__ import annotations

import re
from datetime import datetime

from database.playlist_models import VideoSort

_LEADING_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[_ -]?(?:\d{6}|\d{2}[:_-]\d{2}(?:[:_-]\d{2})?)?[_ -]*")
_DIGITS = re.compile(r"(\d+)")


def natural_key(text: str) -> list[str | int]:
    """Case-insensitive natural order: "Lecture 2" before "Lecture 10"."""
    # re.split with a capture group alternates text and digit runs, so int never meets str in comparison.
    return [int(part) if index % 2 else part.casefold() for index, part in enumerate(_DIGITS.split(text))]


def video_name_key(title: str) -> list[str | int]:
    """Natural order of a video title without its leading Zoom timestamp (as shown in catalogs)."""
    return natural_key(_LEADING_TIMESTAMP.sub("", title, count=1).strip() or title)


def video_sort_key(sort: VideoSort, *, title: str, start_time: datetime | None):
    if sort == "name":
        return video_name_key(title)
    timestamp = start_time.timestamp() if start_time else 0.0
    return -timestamp if sort == "newest" else timestamp
