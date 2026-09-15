"""Channel membership and public Enable/Disable."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.helpers.channel_slug import suggest_slug, validate_channel_slug
from api.helpers.image_upload import delete_key_silent, save_bytes
from api.repositories.channel_repo import ChannelRepository
from api.services.playlist_service import SHARE_NOT_FOUND, UNSET
from database.channel_models import (
    MAX_CHANNELS_PER_USER,
    MAX_PLAYLISTS_PER_CHANNEL,
    MAX_VIDEOS_PER_CHANNEL,
    ChannelModel,
    ChannelPlaylistModel,
    ChannelVideoModel,
)
from database.models import RecordingModel
from database.playlist_models import PlaylistModel
from file_storage.path_builder import StoragePathBuilder, to_storage_key
from logger import get_logger

logger = get_logger()


class ChannelService:
    def __init__(self, session: AsyncSession, user_id: str):
        self.session = session
        self.user_id = user_id
        self.repo = ChannelRepository(session)

    async def _unique_slug(self, slug: str, *, exclude_id: int | None = None) -> str:
        slug = validate_channel_slug(slug)
        stmt = select(ChannelModel.id).where(ChannelModel.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(ChannelModel.id != exclude_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This slug is already taken.")
        return slug

    async def create(self, name: str, *, slug: str | None, description: str | None) -> ChannelModel:
        if await self.repo.count_by_user(self.user_id) >= MAX_CHANNELS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Channels limit reached: {MAX_CHANNELS_PER_USER}",
            )
        raw = slug or suggest_slug(name)
        if len(raw) < 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide a slug of at least 5 characters (letters, digits, hyphens, underscores).",
            )
        final_slug = await self._unique_slug(raw)
        channel = ChannelModel(user_id=self.user_id, name=name, slug=final_slug, description=description)
        self.session.add(channel)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A channel with this name or slug already exists.",
            ) from exc
        return channel

    async def get_owned(self, channel_id: int) -> ChannelModel:
        channel = await self.repo.get_by_id(channel_id, self.user_id)
        if not channel:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
        return channel

    async def update(
        self,
        channel: ChannelModel,
        *,
        name: str | None = None,
        slug: str | None = None,
        description: object = UNSET,
    ) -> ChannelModel:
        if name is not None:
            channel.name = name
        if slug is not None:
            channel.slug = await self._unique_slug(slug, exclude_id=channel.id)
        if description is not UNSET:
            channel.description = description if isinstance(description, str) and description.strip() else None
        channel.updated_at = datetime.now(UTC)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A channel with this name or slug already exists.",
            ) from exc
        return channel

    async def delete(self, channel: ChannelModel) -> None:
        banner = channel.banner_key
        await self.session.delete(channel)
        await self.session.flush()
        await delete_key_silent(banner)

    async def enable_share(self, channel: ChannelModel) -> ChannelModel:
        channel.share_enabled = True
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()
        return channel

    async def disable_share(self, channel: ChannelModel) -> None:
        channel.share_enabled = False
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def set_banner(self, channel: ChannelModel, *, user_slug: int, content: bytes, suffix: str) -> str:
        key = to_storage_key(StoragePathBuilder().channel_banner(user_slug, channel.id, suffix))
        old = channel.banner_key
        await save_bytes(key, content)
        channel.banner_key = key
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()
        if old and old != key:
            await delete_key_silent(old)
        return key

    async def clear_banner(self, channel: ChannelModel) -> None:
        old = channel.banner_key
        channel.banner_key = None
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()
        await delete_key_silent(old)

    async def add_videos(self, channel: ChannelModel, recording_ids: list[int]) -> list[ChannelVideoModel]:
        unique: list[int] = []
        seen: set[int] = set()
        for rid in recording_ids:
            if rid in seen or rid <= 0:
                continue
            seen.add(rid)
            unique.append(rid)
        existing = {row.recording_id for row in await self.repo.list_videos(channel.id)}
        to_add = [rid for rid in unique if rid not in existing]
        if not to_add:
            return []
        current = await self.repo.video_count(channel.id)
        if current + len(to_add) > MAX_VIDEOS_PER_CHANNEL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Channel videos limit reached: {MAX_VIDEOS_PER_CHANNEL}",
            )
        found = {
            rec.id: rec
            for rec in (
                await self.session.execute(
                    select(RecordingModel).where(
                        RecordingModel.id.in_(to_add),
                        RecordingModel.user_id == self.user_id,
                    )
                )
            )
            .scalars()
            .all()
        }
        owned = [rid for rid in to_add if rid in found]
        if not owned:
            return []
        max_pos = await self.repo.max_video_position(channel.id)
        next_pos = (max_pos + 1) if max_pos is not None else 0
        created: list[ChannelVideoModel] = []
        for rid in owned:
            row = ChannelVideoModel(channel_id=channel.id, recording_id=rid, position=next_pos)
            self.session.add(row)
            created.append(row)
            next_pos += 1
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()
        return created

    async def add_videos_from_ids(self, recording: RecordingModel, channel_ids: list[int] | None) -> None:
        if not channel_ids or not recording.user_id:
            return
        ids: list[int] = []
        for raw in channel_ids:
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                continue
            if cid > 0 and cid not in ids:
                ids.append(cid)
        if not ids:
            return
        result = await self.session.execute(
            select(ChannelModel).where(ChannelModel.id.in_(ids), ChannelModel.user_id == recording.user_id)
        )
        channels = list(result.scalars().all())
        for channel in channels:
            try:
                await self.add_videos(channel, [recording.id])
            except HTTPException as exc:
                if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                    logger.warning("Skipping full channel {} for recording {}", channel.id, recording.id)
                    continue
                raise

    async def remove_video(self, channel: ChannelModel, recording_id: int) -> None:
        result = await self.session.execute(
            select(ChannelVideoModel).where(
                ChannelVideoModel.channel_id == channel.id,
                ChannelVideoModel.recording_id == recording_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video is not on this channel")
        await self.session.delete(row)
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def reorder_videos(self, channel: ChannelModel, recording_ids: list[int]) -> None:
        rows = await self.repo.list_videos(channel.id)
        current = {row.recording_id for row in rows}
        if set(recording_ids) != current or len(recording_ids) != len(current):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Video set does not match the channel. Refresh and try again.",
            )
        by_id = {row.recording_id: row for row in rows}
        for position, rid in enumerate(recording_ids):
            by_id[rid].position = position
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def add_playlists(self, channel: ChannelModel, playlist_ids: list[int]) -> list[ChannelPlaylistModel]:
        unique: list[int] = []
        seen: set[int] = set()
        for pid in playlist_ids:
            if pid in seen or pid <= 0:
                continue
            seen.add(pid)
            unique.append(pid)
        existing = {row.playlist_id for row in await self.repo.list_channel_playlists(channel.id)}
        to_add = [pid for pid in unique if pid not in existing]
        if not to_add:
            return []
        current = await self.repo.playlist_count(channel.id)
        if current + len(to_add) > MAX_PLAYLISTS_PER_CHANNEL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Channel playlists limit reached: {MAX_PLAYLISTS_PER_CHANNEL}",
            )
        found = {
            pl.id: pl
            for pl in (
                await self.session.execute(
                    select(PlaylistModel).where(PlaylistModel.id.in_(to_add), PlaylistModel.user_id == self.user_id)
                )
            )
            .scalars()
            .all()
        }
        owned = [pid for pid in to_add if pid in found]
        if not owned:
            return []
        max_pos = await self.repo.max_playlist_position(channel.id)
        next_pos = (max_pos + 1) if max_pos is not None else 0
        created: list[ChannelPlaylistModel] = []
        for pid in owned:
            row = ChannelPlaylistModel(channel_id=channel.id, playlist_id=pid, position=next_pos)
            self.session.add(row)
            created.append(row)
            next_pos += 1
        channel.updated_at = datetime.now(UTC)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This playlist is already on the channel.",
            ) from exc
        return created

    async def remove_playlist(self, channel: ChannelModel, playlist_id: int) -> None:
        result = await self.session.execute(
            select(ChannelPlaylistModel).where(
                ChannelPlaylistModel.channel_id == channel.id,
                ChannelPlaylistModel.playlist_id == playlist_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist is not on this channel")
        await self.session.delete(row)
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def reorder_playlists(self, channel: ChannelModel, playlist_ids: list[int]) -> None:
        rows = await self.repo.list_channel_playlists(channel.id)
        current = {row.playlist_id for row in rows}
        if set(playlist_ids) != current or len(playlist_ids) != len(current):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Playlist set does not match the channel. Refresh and try again.",
            )
        by_id = {row.playlist_id: row for row in rows}
        for position, pid in enumerate(playlist_ids):
            by_id[pid].position = position
        channel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def require_public(self, slug: str) -> ChannelModel:
        channel = await self.repo.get_by_slug(slug)
        if not channel or not channel.share_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SHARE_NOT_FOUND)
        return channel
