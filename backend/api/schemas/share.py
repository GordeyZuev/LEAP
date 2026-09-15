"""Schemas for public share link endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.schemas.source_extras import SourceExtrasResponse
from models.recording import ProcessingStatus


class ShareCreateResponse(BaseModel):
    share_token: uuid.UUID
    share_enabled: bool = True


class ShareStatsSummary(BaseModel):
    view_count: int = 0
    download_count: int = 0
    open_count: int = 0
    last_viewed_at: datetime | None = None
    last_downloaded_at: datetime | None = None


class ShareDailyPoint(BaseModel):
    date: date
    views: int = 0
    downloads: int = 0
    opens: int = 0


class ShareEngagementChapterRow(BaseModel):
    label: str
    count: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)


class ShareEngagementSummary(BaseModel):
    chapter_seeks_top: list[ShareEngagementChapterRow] = Field(default_factory=list)
    completion_rate: float | None = None
    completion_count: int = 0
    view_count_in_range: int = 0
    playlist_navigate_by_from: dict[str, int] | None = None
    watch_exit_median_ratio: float | None = None


class ShareAnalyticsResponse(BaseModel):
    summary: ShareStatsSummary
    daily: list[ShareDailyPoint] = Field(default_factory=list)
    downloads_by_type: dict[str, int] = Field(default_factory=dict)
    engagement: ShareEngagementSummary | None = None


class ShareEngagementEventIn(BaseModel):
    name: Literal["chapter_seek", "playlist_navigate", "playback_complete", "watch_exit"]
    payload: dict[str, object] = Field(default_factory=dict)


class ShareEngagementBatchRequest(BaseModel):
    session_id: str = Field(default="", max_length=64)
    events: list[ShareEngagementEventIn] = Field(default_factory=list, max_length=20)


class PublicRecordingResponse(BaseModel):
    """Public-facing subset of recording data — no user/pipeline internals."""

    id: int
    display_name: str
    title: str
    duration: float = Field(
        description="Processed length in seconds when known, otherwise source length.",
    )
    start_time: datetime
    status: ProcessingStatus

    # AI content — active topic version
    topic_timestamps: Any | None = None
    main_topics: Any | None = None
    summary: str | None = None
    questions: list[str] | None = None

    # Description text (from active topic version)
    description: str | None = None

    # Which download artifacts are available
    available_files: list[str]
    has_processed_video: bool
    has_original_video: bool
    allow_video_download: bool = True
    allow_files_download: bool = True
    # Chat / materials from ingestion (same payload as owner GET .../source-extras).
    # Omitted when file downloads are off. Presigned URLs; not streamed via /files/.
    source_extras: SourceExtrasResponse | None = None

    # Populated when ``view=player`` — avoids a separate /media round-trip.
    play_url: str | None = None
    vtt_url: str | None = None
    original_play_url: str | None = None
    media_expires_in: int | None = None
