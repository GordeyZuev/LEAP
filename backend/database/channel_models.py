"""Channel catalog: ordered videos and playlists owned by one user."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models import Base

if TYPE_CHECKING:
    from database.auth_models import UserModel
    from database.models import RecordingModel
    from database.playlist_models import PlaylistModel

MAX_CHANNELS_PER_USER = 20
MAX_VIDEOS_PER_CHANNEL = 200
MAX_PLAYLISTS_PER_CHANNEL = 200


class ChannelModel(Base):
    """Public catalog of videos and playlists (YouTube-like channel)."""

    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_channels_user_name"),
        UniqueConstraint("slug", name="uq_channels_slug"),
        Index("ix_channels_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    share_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    banner_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
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
    videos: Mapped[list["ChannelVideoModel"]] = relationship(
        "ChannelVideoModel",
        back_populates="channel",
        cascade="all, delete-orphan",
        order_by="ChannelVideoModel.position",
        lazy="noload",
    )
    playlists: Mapped[list["ChannelPlaylistModel"]] = relationship(
        "ChannelPlaylistModel",
        back_populates="channel",
        cascade="all, delete-orphan",
        order_by="ChannelPlaylistModel.position",
        lazy="noload",
    )


class ChannelVideoModel(Base):
    __tablename__ = "channel_videos"
    __table_args__ = (
        UniqueConstraint("channel_id", "recording_id", name="uq_channel_videos_channel_recording"),
        Index("ix_channel_videos_channel_position", "channel_id", "position"),
        Index("ix_channel_videos_recording_id", "recording_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recording_id: Mapped[int] = mapped_column(Integer, ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    channel: Mapped[ChannelModel] = relationship("ChannelModel", back_populates="videos")
    recording: Mapped["RecordingModel"] = relationship("RecordingModel", lazy="selectin")


class ChannelPlaylistModel(Base):
    __tablename__ = "channel_playlists"
    __table_args__ = (
        UniqueConstraint("channel_id", "playlist_id", name="uq_channel_playlists_channel_playlist"),
        Index("ix_channel_playlists_channel_position", "channel_id", "position"),
        Index("ix_channel_playlists_playlist_id", "playlist_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    playlist_id: Mapped[int] = mapped_column(Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    channel: Mapped[ChannelModel] = relationship("ChannelModel", back_populates="playlists")
    playlist: Mapped["PlaylistModel"] = relationship("PlaylistModel", lazy="selectin")
