"""Share link access events for anonymous public traffic analytics."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from ulid import ULID

from database.models import Base


class ShareEventType:
    PAGE_VIEW = "page_view"
    FILE_DOWNLOAD = "file_download"


class ShareArtifactType:
    SRT = "srt"
    VTT = "vtt"
    TRANSCRIPT_JSON = "transcript_json"
    TRANSCRIPT_TXT = "transcript_txt"
    TRANSCRIPT_WORDS = "transcript_words"
    VIDEO_PROCESSED = "video_processed"
    VIDEO_ORIGINAL = "video_original"


class ShareAccessEventModel(Base):
    """Immutable log of anonymous share page views and artifact downloads."""

    __tablename__ = "share_access_events"
    __table_args__ = (
        Index("ix_share_access_events_recording_created", "recording_id", "created_at"),
        Index("ix_share_access_events_dedup", "recording_id", "event_type", "visitor_key", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ULID()))
    recording_id: Mapped[int] = mapped_column(Integer, ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visitor_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
