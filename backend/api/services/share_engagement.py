"""Best-effort ingest and owner aggregates for public watch engagement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.share_engagement_repo import ShareEngagementRepository
from api.schemas.share import (
    ShareEngagementBatchRequest,
    ShareEngagementChapterRow,
    ShareEngagementSummary,
)
from api.services.share_observability import visitor_key_for_request
from database.share_models import ShareEngagementEventModel, ShareEngagementEventName
from logger import get_logger

logger = get_logger("share.engagement")

MAX_BATCH_EVENTS = 20
MAX_BODY_BYTES = 32 * 1024
MAX_SESSION_ID_LEN = 64
MAX_LABEL_LEN = 120

ALLOWED_EVENT_NAMES = frozenset(
    {
        ShareEngagementEventName.CHAPTER_SEEK,
        ShareEngagementEventName.PLAYLIST_NAVIGATE,
        ShareEngagementEventName.PLAYBACK_COMPLETE,
        ShareEngagementEventName.WATCH_EXIT,
    }
)

_CHAPTER_SOURCES = frozenset({"marker", "sidebar", "transcript"})
_NAV_FROM = frozenset({"sidebar", "landing", "autoplay", "url"})


@dataclass(frozen=True, slots=True)
class EngagementContext:
    owner_user_id: str
    recording_id: int | None = None
    playlist_id: int | None = None
    channel_id: int | None = None
    visitor_subject: str = "engagement"
    expected_nav_item_id: int | None = None


def parse_engagement_batch(raw: bytes) -> ShareEngagementBatchRequest | None:
    """Parse and validate batch body; None when over limit or malformed (caller returns 204)."""
    if len(raw) > MAX_BODY_BYTES:
        return None
    if not raw.strip():
        return ShareEngagementBatchRequest()
    try:
        return ShareEngagementBatchRequest.model_validate_json(raw)
    except ValidationError:
        return None


def normalize_event(name: str, payload: dict | None) -> tuple[str, dict] | None:
    if name not in ALLOWED_EVENT_NAMES:
        return None
    raw = payload or {}
    if not isinstance(raw, dict):
        return None
    if name == ShareEngagementEventName.CHAPTER_SEEK:
        source = raw.get("source")
        if source not in _CHAPTER_SOURCES:
            return None
        try:
            time_sec = int(raw.get("time_sec", -1))
        except (TypeError, ValueError):
            return None
        if time_sec < 0:
            return None
        label = str(raw.get("label") or "")[:MAX_LABEL_LEN]
        return name, {"source": source, "time_sec": time_sec, "label": label}
    if name == ShareEngagementEventName.PLAYLIST_NAVIGATE:
        nav_from = raw.get("from")
        if nav_from not in _NAV_FROM:
            return None
        try:
            to_item_id = int(raw.get("to_item_id"))
        except (TypeError, ValueError):
            return None
        if to_item_id <= 0:
            return None
        return name, {"from": nav_from, "to_item_id": to_item_id}
    if name == ShareEngagementEventName.PLAYBACK_COMPLETE:
        return name, {}
    if name == ShareEngagementEventName.WATCH_EXIT:
        try:
            position_sec = int(raw.get("position_sec", -1))
            duration_sec = int(raw.get("duration_sec", 0))
        except (TypeError, ValueError):
            return None
        if position_sec < 0 or duration_sec <= 0:
            return None
        position_sec = min(position_sec, duration_sec)
        return name, {"position_sec": position_sec, "duration_sec": duration_sec}
    return None


class ShareEngagementService:
    async def record_batch(
        self,
        session: AsyncSession,
        *,
        context: EngagementContext,
        request: Request,
        session_id: str,
        events: list[dict],
    ) -> None:
        if not context.owner_user_id or not events:
            return
        sid = (session_id or "")[:MAX_SESSION_ID_LEN]
        visitor_key = visitor_key_for_request(context.visitor_subject, request)
        rows: list[ShareEngagementEventModel] = []
        for item in events[:MAX_BATCH_EVENTS]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or name not in ALLOWED_EVENT_NAMES:
                continue
            normalized = normalize_event(name, item.get("payload"))
            if normalized is None:
                continue
            event_name, payload = normalized
            if (
                event_name == ShareEngagementEventName.PLAYLIST_NAVIGATE
                and context.expected_nav_item_id is not None
                and payload.get("to_item_id") != context.expected_nav_item_id
            ):
                continue
            rows.append(
                ShareEngagementEventModel(
                    owner_user_id=context.owner_user_id,
                    recording_id=context.recording_id,
                    playlist_id=context.playlist_id,
                    channel_id=context.channel_id,
                    event_name=event_name,
                    visitor_key=visitor_key,
                    session_id=sid,
                    payload=payload,
                )
            )
        if not rows:
            return
        repo = ShareEngagementRepository(session)
        await repo.insert_many(rows)
        await session.commit()

    async def build_summary(
        self,
        session: AsyncSession,
        *,
        from_dt: datetime,
        to_dt: datetime,
        recording_id: int | None = None,
        recording_ids: list[int] | None = None,
        playlist_id: int | None = None,
        include_playlist_navigation: bool = False,
        owner_user_id: str | None = None,
    ) -> ShareEngagementSummary | None:
        repo = ShareEngagementRepository(session)
        ids = [recording_id] if recording_id is not None else (recording_ids or [])
        if recording_id is None and not ids and not include_playlist_navigation:
            return None

        views = await repo.count_page_views_in_range(recording_ids=ids, from_dt=from_dt, to_dt=to_dt)
        completes = await repo.count_event(
            ShareEngagementEventName.PLAYBACK_COMPLETE,
            recording_id=recording_id,
            recording_ids=recording_ids if recording_id is None else None,
            from_dt=from_dt,
            to_dt=to_dt,
            owner_user_id=owner_user_id,
        )
        chapter_seeks_top = await repo.chapter_seeks_top(
            recording_id=recording_id,
            recording_ids=recording_ids if recording_id is None else None,
            from_dt=from_dt,
            to_dt=to_dt,
            owner_user_id=owner_user_id,
        )
        median = await repo.watch_exit_median_ratio(
            recording_id=recording_id,
            recording_ids=recording_ids if recording_id is None else None,
            from_dt=from_dt,
            to_dt=to_dt,
            owner_user_id=owner_user_id,
        )
        navigate: dict[str, int] | None = None
        if include_playlist_navigation and playlist_id is not None:
            navigate = await repo.playlist_navigate_by_from(
                playlist_id, from_dt=from_dt, to_dt=to_dt, owner_user_id=owner_user_id
            )

        has_data = bool(chapter_seeks_top or completes or median is not None or (navigate and sum(navigate.values())))
        if not has_data:
            return None

        completion_rate = (completes / views) if views > 0 else None
        return ShareEngagementSummary(
            chapter_seeks_top=[ShareEngagementChapterRow.model_validate(row) for row in chapter_seeks_top],
            completion_rate=completion_rate,
            completion_count=completes,
            view_count_in_range=views,
            playlist_navigate_by_from=navigate,
            watch_exit_median_ratio=median,
        )
