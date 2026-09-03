"""Schemas for public share link endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from models.recording import ProcessingStatus


class ShareCreateResponse(BaseModel):
    share_token: uuid.UUID


class ShareStatsSummary(BaseModel):
    view_count: int = 0
    download_count: int = 0
    last_viewed_at: datetime | None = None
    last_downloaded_at: datetime | None = None


class ShareDailyPoint(BaseModel):
    date: date
    views: int = 0
    downloads: int = 0


class ShareAnalyticsResponse(BaseModel):
    summary: ShareStatsSummary
    daily: list[ShareDailyPoint] = Field(default_factory=list)
    downloads_by_type: dict[str, int] = Field(default_factory=dict)


class PublicRecordingResponse(BaseModel):
    """Public-facing subset of recording data — no user/pipeline internals."""

    id: int
    display_name: str
    duration: float
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
