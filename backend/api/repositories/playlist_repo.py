"""Playlist repository — tenant-scoped queries only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

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
                selectinload(PlaylistModel.items)
                .selectinload(PlaylistItemModel.recording)
                .selectinload(RecordingModel.owner),
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

    async def list_page(
        self,
        user_id: str,
        *,
        q: str | None,
        page: int,
        per_page: int,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[PlaylistModel], int]:
        """Paginated playlists for a user (SQL offset/limit)."""
        base = select(PlaylistModel).where(PlaylistModel.user_id == user_id)
        if q and q.strip():
            base = base.where(PlaylistModel.name.ilike(f"%{q.strip()}%"))

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        order_col = getattr(PlaylistModel, sort_by, PlaylistModel.updated_at)
        order = order_col.desc() if sort_order == "desc" else order_col.asc()
        offset = (page - 1) * per_page
        data_stmt = base.order_by(order).offset(offset).limit(per_page)
        result = await self.session.execute(data_stmt)
        return list(result.scalars().unique().all()), total

    async def aggregate_stats(self, playlist_ids: list[int]) -> dict[int, tuple[int, float]]:
        """Return playlist_id -> (item_count, duration_sum) without hydrating items."""
        if not playlist_ids:
            return {}
        duration = func.coalesce(RecordingModel.final_duration, RecordingModel.duration, 0.0)
        result = await self.session.execute(
            select(
                PlaylistItemModel.playlist_id,
                func.count(PlaylistItemModel.id),
                func.coalesce(func.sum(duration), 0.0),
            )
            .join(RecordingModel, RecordingModel.id == PlaylistItemModel.recording_id)
            .where(PlaylistItemModel.playlist_id.in_(playlist_ids))
            .group_by(PlaylistItemModel.playlist_id)
        )
        return {int(pid): (int(count), float(total)) for pid, count, total in result.all()}

    async def first_playable_recordings(self, playlist_ids: list[int]) -> dict[int, RecordingModel]:
        """First course item per playlist (watch order), one query. Used for auto cover."""
        if not playlist_ids:
            return {}
        playable = (
            RecordingModel.deleted.is_(False)
            & (RecordingModel.delete_state == "active")
            & (RecordingModel.blank_record.is_(False))
        )
        ranked = (
            select(
                PlaylistItemModel.playlist_id.label("playlist_id"),
                PlaylistItemModel.recording_id.label("recording_id"),
                func.row_number()
                .over(partition_by=PlaylistItemModel.playlist_id, order_by=PlaylistItemModel.position)
                .label("rn"),
            )
            .join(RecordingModel, RecordingModel.id == PlaylistItemModel.recording_id)
            .where(PlaylistItemModel.playlist_id.in_(playlist_ids), playable)
        ).subquery()
        result = await self.session.execute(
            select(ranked.c.playlist_id, RecordingModel)
            .join(RecordingModel, RecordingModel.id == ranked.c.recording_id)
            .where(ranked.c.rn == 1)
            .options(
                noload(RecordingModel.owner),
                noload(RecordingModel.input_source),
                noload(RecordingModel.template),
                noload(RecordingModel.source),
                noload(RecordingModel.outputs),
                noload(RecordingModel.processing_stages),
            )
        )
        return {int(pid): rec for pid, rec in result.all()}

    async def item_titles_by_playlist(self, playlist_ids: list[int]) -> dict[int, list[tuple[int, str]]]:
        """Ordered (recording_id, display_name) per playlist for Jinja {{ items }}."""
        if not playlist_ids:
            return {}
        result = await self.session.execute(
            select(PlaylistItemModel.playlist_id, RecordingModel.id, RecordingModel.display_name)
            .join(RecordingModel, RecordingModel.id == PlaylistItemModel.recording_id)
            .where(PlaylistItemModel.playlist_id.in_(playlist_ids))
            .order_by(PlaylistItemModel.playlist_id, PlaylistItemModel.position)
        )
        out: dict[int, list[tuple[int, str]]] = {}
        for playlist_id, rec_id, name in result.all():
            out.setdefault(int(playlist_id), []).append((int(rec_id), str(name)))
        return out

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
