"""Playlist and playlist-item models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models import Base

if TYPE_CHECKING:
    from database.auth_models import UserModel
    from database.models import RecordingModel

MAX_PLAYLISTS_PER_USER = 200
MAX_ITEMS_PER_PLAYLIST = 200


class PlaylistModel(Base):
    """Ordered collection of recordings owned by one user."""

    __tablename__ = "playlists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_playlists_user_name"),
        UniqueConstraint("share_token", name="uq_playlists_share_token"),
        Index("ix_playlists_share_token", "share_token", postgresql_where=None),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    share_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    share_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    owner: Mapped["UserModel"] = relationship("UserModel", lazy="selectin")
    items: Mapped[list["PlaylistItemModel"]] = relationship(
        "PlaylistItemModel",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistItemModel.position",
        lazy="selectin",
    )


class PlaylistItemModel(Base):
    """One recording in a playlist, with a stable public item id."""

    __tablename__ = "playlist_items"
    __table_args__ = (
        UniqueConstraint("playlist_id", "recording_id", name="uq_playlist_items_playlist_recording"),
        Index("ix_playlist_items_playlist_position", "playlist_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recording_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    playlist: Mapped[PlaylistModel] = relationship("PlaylistModel", back_populates="items", lazy="selectin")
    recording: Mapped["RecordingModel"] = relationship("RecordingModel", lazy="selectin")
