"""Share link access events for anonymous public traffic analytics."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
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
    recording_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True
    )
    playlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=True
    )
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=True
    )
    owner_user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visitor_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class ShareEngagementEventName:
    CHAPTER_SEEK = "chapter_seek"
    PLAYLIST_NAVIGATE = "playlist_navigate"
    PLAYBACK_COMPLETE = "playback_complete"
    WATCH_EXIT = "watch_exit"


class ShareEngagementEventModel(Base):
    """Immutable log of anonymous public watch engagement (seeks, completion, navigation)."""

    __tablename__ = "share_engagement_events"
    __table_args__ = (
        Index("ix_share_engagement_recording_created", "recording_id", "created_at"),
        Index("ix_share_engagement_playlist_created", "playlist_id", "created_at"),
        Index("ix_share_engagement_owner_created", "owner_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ULID()))
    owner_user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recording_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True
    )
    playlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=True
    )
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=True
    )
    event_name: Mapped[str] = mapped_column(String(32), nullable=False)
    visitor_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
