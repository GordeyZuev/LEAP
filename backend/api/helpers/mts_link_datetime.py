"""MTS Link lecture timestamps: session start, not recording-file createAt."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from api.mts_link_api import MtsLinkAPIError, unwrap_data_object
from api.shared.exceptions import ExternalRateLimitError

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# UserAPI mixes ``+03:00`` and ``+0300``. fromisoformat needs a colon.
_OFFSET_NO_COLON = re.compile(r"([+-])(\d{2})(\d{2})$")


def parse_mts_link_datetime(value: str | None) -> datetime | None:
    """Parse a UserAPI datetime. Naive wall times are Europe/Moscow, not UTC.

    Returns None when the value is missing or unparseable so backfill can skip
    instead of inventing ``now()``.
    """
    if not value or not str(value).strip():
        return None
    text = str(value).strip().replace("Z", "+00:00")
    text = _OFFSET_NO_COLON.sub(r"\1\2:\3", text)
    for parser in (datetime.fromisoformat, lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M:%S")):
        try:
            parsed = parser(text)
        except (ValueError, TypeError):
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=MOSCOW_TZ)
        return parsed
    return None


def _from_unix(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def resolve_mts_link_start_time(
    record: dict[str, Any] | None,
    session: dict[str, Any] | None,
    *,
    allow_now: bool = True,
) -> tuple[datetime | None, str]:
    """Pick the lecture start. Source tag is startsAt, utcStartsAt, estimatedAt, createAt, or now."""
    session = session if isinstance(session, dict) else {}
    record = record if isinstance(record, dict) else {}

    starts = parse_mts_link_datetime(session.get("startsAt") if isinstance(session.get("startsAt"), str) else None)
    if starts is not None:
        return starts, "startsAt"

    utc_starts = _from_unix(session.get("utcStartsAt"))
    if utc_starts is not None:
        return utc_starts, "utcStartsAt"

    estimated = parse_mts_link_datetime(
        session.get("estimatedAt") if isinstance(session.get("estimatedAt"), str) else None
    )
    if estimated is not None:
        return estimated, "estimatedAt"

    created = parse_mts_link_datetime(record.get("createAt") if isinstance(record.get("createAt"), str) else None)
    if created is not None:
        return created, "createAt"

    if allow_now:
        return datetime.now(UTC), "now"
    return None, "skip"


def session_starts_at_iso(session: dict[str, Any] | None) -> str | None:
    """ISO for ``source.meta.session_starts_at`` only when the event session has a start."""
    if not isinstance(session, dict):
        return None
    starts = parse_mts_link_datetime(session.get("startsAt") if isinstance(session.get("startsAt"), str) else None)
    if starts is not None:
        return starts.isoformat()
    utc_starts = _from_unix(session.get("utcStartsAt"))
    if utc_starts is not None:
        return utc_starts.isoformat()
    estimated = parse_mts_link_datetime(
        session.get("estimatedAt") if isinstance(session.get("estimatedAt"), str) else None
    )
    if estimated is not None:
        return estimated.isoformat()
    return None


async def load_event_session(
    mts_api: Any,
    session_id: Any,
    cache: dict[Any, dict[str, Any] | None],
    *,
    pause_seconds: float = 0.0,
) -> dict[str, Any] | None:
    """GET /eventsessions/{id} once per ``session_id`` in this cache. Errors cache as None."""
    if session_id in (None, ""):
        return None
    if session_id in cache:
        return cache[session_id]
    try:
        payload = await mts_api.get_event_session(session_id)
    except (MtsLinkAPIError, ExternalRateLimitError):
        cache[session_id] = None
        if pause_seconds > 0:
            await asyncio.sleep(pause_seconds)
        return None
    session = unwrap_data_object(payload) if isinstance(payload, dict) else None
    if not session:
        session = payload if isinstance(payload, dict) else None
    cache[session_id] = session
    if pause_seconds > 0:
        await asyncio.sleep(pause_seconds)
    return session
