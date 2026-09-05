"""Playlist repository — tenant-scoped queries only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import RecordingModel
from database.playlist_models import PlaylistItemModel, PlaylistModel


class PlaylistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, playlist_id: int, user_id: str) -> PlaylistModel | None:
        result = await self.session.execute(
            select(PlaylistModel)
            .options(selectinload(PlaylistModel.items).selectinload(PlaylistItemModel.recording))
            .where(PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_share_token(self, token) -> PlaylistModel | None:
        result = await self.session.execute(
            select(PlaylistModel)
            .options(
                selectinload(PlaylistModel.owner),
                selectinload(PlaylistModel.items).selectinload(PlaylistItemModel.recording),
            )
            .where(PlaylistModel.share_token == token)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[PlaylistModel]:
        result = await self.session.execute(
            select(PlaylistModel)
            .options(selectinload(PlaylistModel.items).selectinload(PlaylistItemModel.recording))
            .where(PlaylistModel.user_id == user_id)
            .order_by(PlaylistModel.updated_at.desc())
        )
        return list(result.scalars().unique().all())

    async def count_by_user(self, user_id: str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(PlaylistModel).where(PlaylistModel.user_id == user_id)
        )
        return int(result.scalar_one())

    async def summaries_for_recording(self, recording_id: int, user_id: str) -> list[tuple[PlaylistModel, int]]:
        result = await self.session.execute(
            select(PlaylistModel, PlaylistItemModel.id)
            .join(PlaylistItemModel, PlaylistItemModel.playlist_id == PlaylistModel.id)
            .where(PlaylistItemModel.recording_id == recording_id, PlaylistModel.user_id == user_id)
            .order_by(PlaylistModel.name)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def get_item(self, item_id: int, playlist_id: int) -> PlaylistItemModel | None:
        result = await self.session.execute(
            select(PlaylistItemModel)
            .options(selectinload(PlaylistItemModel.recording))
            .where(PlaylistItemModel.id == item_id, PlaylistItemModel.playlist_id == playlist_id)
        )
        return result.scalar_one_or_none()

    async def list_items(
        self,
        playlist_id: int,
        *,
        q: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[PlaylistItemModel]:
        stmt = (
            select(PlaylistItemModel)
            .options(selectinload(PlaylistItemModel.recording))
            .join(RecordingModel, RecordingModel.id == PlaylistItemModel.recording_id)
            .where(PlaylistItemModel.playlist_id == playlist_id)
        )
        if q and q.strip():
            stmt = stmt.where(RecordingModel.display_name.ilike(f"%{q.strip()}%"))
        if from_date is not None:
            stmt = stmt.where(RecordingModel.start_time >= from_date)
        if to_date is not None:
            stmt = stmt.where(RecordingModel.start_time <= to_date)
        stmt = stmt.order_by(PlaylistItemModel.position)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def max_position(self, playlist_id: int) -> int | None:
        result = await self.session.execute(
            select(func.max(PlaylistItemModel.position)).where(PlaylistItemModel.playlist_id == playlist_id)
        )
        return result.scalar_one()

    async def item_count(self, playlist_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(PlaylistItemModel).where(PlaylistItemModel.playlist_id == playlist_id)
        )
        return int(result.scalar_one())
