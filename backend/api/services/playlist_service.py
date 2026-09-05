"""Playlist membership, share links, and template bind hook."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.playlist_repo import PlaylistRepository
from database.models import RecordingModel
from database.playlist_models import MAX_ITEMS_PER_PLAYLIST, MAX_PLAYLISTS_PER_USER, PlaylistItemModel, PlaylistModel
from database.template_models import RecordingTemplateModel
from logger import get_logger

logger = get_logger()

SHARE_NOT_FOUND = "Share link not found or has been revoked"
UNSET = object()


def item_unavailable_reason(recording: RecordingModel) -> str | None:
    """Return a public reason when the recording cannot be played, else None."""
    if recording.deleted or recording.delete_state != "active":
        return "deleted"
    if recording.blank_record:
        return "blank"
    if not recording.processed_video_path:
        return "not_ready"
    return None


def is_playable(recording: RecordingModel) -> bool:
    return item_unavailable_reason(recording) is None


def assert_public_download(*, allow_video: bool, allow_files: bool, kind: str, inline: bool = False) -> None:
    """Raise 403 when a public download is disabled. Inline player fetches always pass."""
    if inline:
        return
    if kind == "video" and not allow_video:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Video download is not allowed")
    if kind == "files" and not allow_files:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="File download is not allowed")


class PlaylistService:
    def __init__(self, session: AsyncSession, user_id: str):
        self.session = session
        self.user_id = user_id
        self.repo = PlaylistRepository(session)

    async def create(self, name: str, description: str | None) -> PlaylistModel:
        if await self.repo.count_by_user(self.user_id) >= MAX_PLAYLISTS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Playlists limit reached: {MAX_PLAYLISTS_PER_USER}",
            )
        playlist = PlaylistModel(user_id=self.user_id, name=name, description=description)
        self.session.add(playlist)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A playlist with this name already exists.",
            ) from exc
        return playlist

    async def get_owned(self, playlist_id: int) -> PlaylistModel:
        playlist = await self.repo.get_by_id(playlist_id, self.user_id)
        if not playlist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
        return playlist

    async def update(
        self,
        playlist: PlaylistModel,
        *,
        name: str | None = None,
        description: object = UNSET,
    ) -> PlaylistModel:
        if name is not None:
            playlist.name = name
        if description is not UNSET:
            playlist.description = description if isinstance(description, str) and description.strip() else None
        playlist.updated_at = datetime.now(UTC)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A playlist with this name already exists.",
            ) from exc
        return playlist

    async def delete(self, playlist: PlaylistModel) -> None:
        await self.session.delete(playlist)
        await self.session.flush()

    async def add_items(self, playlist: PlaylistModel, recording_ids: list[int]) -> list[PlaylistItemModel]:
        """Append recordings. Duplicates and missing ids are skipped / 404 as specified."""
        unique_ids: list[int] = []
        seen: set[int] = set()
        for rid in recording_ids:
            if rid in seen:
                continue
            seen.add(rid)
            unique_ids.append(rid)

        existing = {item.recording_id for item in playlist.items}
        to_add = [rid for rid in unique_ids if rid not in existing]
        if not to_add:
            return []

        current_count = len(playlist.items)
        if current_count + len(to_add) > MAX_ITEMS_PER_PLAYLIST:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Playlist items limit reached: {MAX_ITEMS_PER_PLAYLIST}",
            )

        result = await self.session.execute(
            select(RecordingModel).where(
                RecordingModel.id.in_(to_add),
                RecordingModel.user_id == self.user_id,
            )
        )
        found = {rec.id: rec for rec in result.scalars().all()}
        missing = [rid for rid in to_add if rid not in found]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

        max_pos = await self.repo.max_position(playlist.id)
        next_pos = (max_pos + 1) if max_pos is not None else 0
        created: list[PlaylistItemModel] = []
        for rid in to_add:
            item = PlaylistItemModel(playlist_id=playlist.id, recording_id=rid, position=next_pos)
            self.session.add(item)
            playlist.items.append(item)
            created.append(item)
            next_pos += 1
        playlist.updated_at = datetime.now(UTC)
        await self.session.flush()
        return created

    async def remove_item(self, playlist: PlaylistModel, item_id: int) -> None:
        item = await self.repo.get_item(item_id, playlist.id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist item not found")
        await self.session.delete(item)
        playlist.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def reorder(self, playlist: PlaylistModel, item_ids: list[int]) -> None:
        current_ids = {item.id for item in playlist.items}
        if set(item_ids) != current_ids or len(item_ids) != len(current_ids):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Item set does not match the playlist. Refresh and try again.",
            )
        by_id = {item.id: item for item in playlist.items}
        for position, item_id in enumerate(item_ids):
            by_id[item_id].position = position
        playlist.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def enable_share(self, playlist: PlaylistModel) -> PlaylistModel:
        if playlist.share_token is None:
            playlist.share_token = uuid.uuid4()
            playlist.share_created_at = datetime.now(UTC)
        playlist.share_enabled = True
        playlist.updated_at = datetime.now(UTC)
        await self.session.flush()
        return playlist

    async def disable_share(self, playlist: PlaylistModel) -> None:
        playlist.share_enabled = False
        playlist.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def rotate_share(self, playlist: PlaylistModel) -> PlaylistModel:
        playlist.share_token = uuid.uuid4()
        playlist.share_created_at = datetime.now(UTC)
        playlist.share_enabled = True
        playlist.updated_at = datetime.now(UTC)
        await self.session.flush()
        return playlist

    async def add_from_template(self, recording: RecordingModel) -> None:
        """Append recording to named-template playlist_ids. No-op for default template."""
        if not recording.template_id:
            return
        result = await self.session.execute(
            select(RecordingTemplateModel).where(
                RecordingTemplateModel.id == recording.template_id,
                RecordingTemplateModel.user_id == self.user_id,
            )
        )
        template = result.scalar_one_or_none()
        if not template or template.is_default:
            return
        raw_ids = (template.output_config or {}).get("playlist_ids") or []
        await self._add_recording_to_playlist_ids(recording, raw_ids)

    async def add_from_playlist_ids(self, recording: RecordingModel, playlist_ids: list[int] | None) -> None:
        if not playlist_ids:
            return
        await self._add_recording_to_playlist_ids(recording, playlist_ids)

    async def _add_recording_to_playlist_ids(self, recording: RecordingModel, playlist_ids: list) -> None:
        ids: list[int] = []
        for raw in playlist_ids:
            try:
                pid = int(raw)
            except (TypeError, ValueError):
                continue
            if pid > 0 and pid not in ids:
                ids.append(pid)
        if not ids:
            return
        for playlist_id in ids:
            playlist = await self.repo.get_by_id(playlist_id, self.user_id)
            if not playlist:
                continue
            try:
                await self.add_items(playlist, [recording.id])
            except HTTPException as exc:
                if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                    logger.warning("Skipping full playlist {} for recording {}", playlist_id, recording.id)
                    continue
                raise


async def poster_url_map(session: AsyncSession, user_id: str, recordings: list) -> dict[int, str]:
    """Presigned poster URLs keyed by recording id. Missing files are omitted."""
    from api.routers.recordings import _poster_urls

    recs = [rec for rec in recordings if rec is not None]
    if not recs:
        return {}
    previews = await _poster_urls(session, user_id, recs)
    return {rid: preview.url for rid, preview in previews.items() if preview.url}


async def add_from_bound_template(session: AsyncSession, user_id: str, recording: RecordingModel) -> None:
    """Call after template_id is newly set. Safe no-op when nothing to add."""
    await PlaylistService(session, user_id).add_from_template(recording)


async def add_from_output_override(
    session: AsyncSession, user_id: str, recording: RecordingModel, output_config: dict | None
) -> None:
    """Add recording to playlists listed in a Run output override. Empty list is a no-op."""
    if not output_config:
        return
    await PlaylistService(session, user_id).add_from_playlist_ids(recording, output_config.get("playlist_ids"))
