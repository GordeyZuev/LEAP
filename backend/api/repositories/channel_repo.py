"""Channel repository — tenant-scoped, no membership hydration on list."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from database.channel_models import ChannelModel, ChannelPlaylistModel, ChannelVideoModel
from database.models import RecordingModel
from database.playlist_models import PlaylistItemModel, PlaylistModel

# Public catalog only needs row columns (name, duration, poster keys, topics).
_RECORDING_SKIP_GRAPHS = (
    noload(RecordingModel.owner),
    noload(RecordingModel.input_source),
    noload(RecordingModel.template),
    noload(RecordingModel.source),
    noload(RecordingModel.outputs),
    noload(RecordingModel.processing_stages),
)
_PLAYLIST_SKIP_GRAPHS = (
    noload(PlaylistModel.items),
    noload(PlaylistModel.owner),
)


def playable_recording_clause():
    return (
        RecordingModel.deleted.is_(False)
        & (RecordingModel.delete_state == "active")
        & (RecordingModel.blank_record.is_(False))
        & RecordingModel.processed_video_path.is_not(None)
        & (RecordingModel.processed_video_path != "")
    )


class ChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, channel_id: int, user_id: str) -> ChannelModel | None:
        result = await self.session.execute(
            select(ChannelModel).where(ChannelModel.id == channel_id, ChannelModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> ChannelModel | None:
        result = await self.session.execute(select(ChannelModel).where(ChannelModel.slug == slug))
        return result.scalar_one_or_none()

    async def count_by_user(self, user_id: str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(ChannelModel).where(ChannelModel.user_id == user_id)
        )
        return int(result.scalar_one())

    async def list_page(
        self,
        user_id: str,
        *,
        q: str | None,
        page: int,
        per_page: int,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[ChannelModel], int]:
        base = select(ChannelModel).where(ChannelModel.user_id == user_id)
        if q and q.strip():
            term = f"%{q.strip()}%"
            base = base.where(or_(ChannelModel.name.ilike(term), ChannelModel.slug.ilike(term)))
        total = int((await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        order_col = getattr(ChannelModel, sort_by, ChannelModel.updated_at)
        order = order_col.desc() if sort_order == "desc" else order_col.asc()
        offset = (page - 1) * per_page
        result = await self.session.execute(base.order_by(order).offset(offset).limit(per_page))
        return list(result.scalars().unique().all()), total

    async def membership_counts(self, channel_ids: list[int]) -> dict[int, tuple[int, int]]:
        """channel_id -> (video_count, playlist_count)."""
        if not channel_ids:
            return {}
        videos = await self.session.execute(
            select(ChannelVideoModel.channel_id, func.count())
            .where(ChannelVideoModel.channel_id.in_(channel_ids))
            .group_by(ChannelVideoModel.channel_id)
        )
        playlists = await self.session.execute(
            select(ChannelPlaylistModel.channel_id, func.count())
            .where(ChannelPlaylistModel.channel_id.in_(channel_ids))
            .group_by(ChannelPlaylistModel.channel_id)
        )
        out: dict[int, tuple[int, int]] = dict.fromkeys(channel_ids, (0, 0))
        video_map = {int(cid): int(n) for cid, n in videos.all()}
        playlist_map = {int(cid): int(n) for cid, n in playlists.all()}
        for cid in channel_ids:
            out[cid] = (video_map.get(cid, 0), playlist_map.get(cid, 0))
        return out

    async def list_videos(self, channel_id: int) -> list[ChannelVideoModel]:
        result = await self.session.execute(
            select(ChannelVideoModel)
            .where(ChannelVideoModel.channel_id == channel_id)
            .order_by(ChannelVideoModel.position)
        )
        return list(result.scalars().unique().all())

    async def list_channel_playlists(self, channel_id: int) -> list[ChannelPlaylistModel]:
        result = await self.session.execute(
            select(ChannelPlaylistModel)
            .where(ChannelPlaylistModel.channel_id == channel_id)
            .order_by(ChannelPlaylistModel.position)
        )
        return list(result.scalars().unique().all())

    async def max_video_position(self, channel_id: int) -> int | None:
        result = await self.session.execute(
            select(func.max(ChannelVideoModel.position)).where(ChannelVideoModel.channel_id == channel_id)
        )
        return result.scalar_one()

    async def max_playlist_position(self, channel_id: int) -> int | None:
        result = await self.session.execute(
            select(func.max(ChannelPlaylistModel.position)).where(ChannelPlaylistModel.channel_id == channel_id)
        )
        return result.scalar_one()

    async def video_count(self, channel_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(ChannelVideoModel).where(ChannelVideoModel.channel_id == channel_id)
        )
        return int(result.scalar_one())

    async def playlist_count(self, channel_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(ChannelPlaylistModel).where(ChannelPlaylistModel.channel_id == channel_id)
        )
        return int(result.scalar_one())

    async def summaries_for_recording(self, recording_id: int, user_id: str) -> list[tuple[ChannelModel, int]]:
        result = await self.session.execute(
            select(ChannelModel, ChannelVideoModel.id)
            .join(ChannelVideoModel, ChannelVideoModel.channel_id == ChannelModel.id)
            .where(ChannelVideoModel.recording_id == recording_id, ChannelModel.user_id == user_id)
            .order_by(ChannelModel.name)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def summaries_for_playlist(self, playlist_id: int, user_id: str) -> list[tuple[ChannelModel, int]]:
        result = await self.session.execute(
            select(ChannelModel, ChannelPlaylistModel.id)
            .join(ChannelPlaylistModel, ChannelPlaylistModel.channel_id == ChannelModel.id)
            .where(ChannelPlaylistModel.playlist_id == playlist_id, ChannelModel.user_id == user_id)
            .order_by(ChannelModel.name)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def public_videos(self, channel_id: int) -> list[tuple[ChannelVideoModel, RecordingModel]]:
        result = await self.session.execute(
            select(ChannelVideoModel, RecordingModel)
            .join(RecordingModel, RecordingModel.id == ChannelVideoModel.recording_id)
            .where(
                ChannelVideoModel.channel_id == channel_id,
                RecordingModel.share_enabled.is_(True),
                RecordingModel.share_token.is_not(None),
                playable_recording_clause(),
            )
            .options(*_RECORDING_SKIP_GRAPHS)
            .order_by(ChannelVideoModel.position)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def public_playlists(self, channel_id: int) -> list[tuple[ChannelPlaylistModel, PlaylistModel]]:
        result = await self.session.execute(
            select(ChannelPlaylistModel, PlaylistModel)
            .join(PlaylistModel, PlaylistModel.id == ChannelPlaylistModel.playlist_id)
            .where(
                ChannelPlaylistModel.channel_id == channel_id,
                PlaylistModel.share_enabled.is_(True),
                PlaylistModel.share_token.is_not(None),
            )
            .options(*_PLAYLIST_SKIP_GRAPHS)
            .order_by(ChannelPlaylistModel.position)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def recording_ids_in_channel_scope(self, channel_id: int) -> list[int]:
        """Videos on the channel plus items of attached playlists (current membership)."""
        video_ids = await self.session.execute(
            select(ChannelVideoModel.recording_id).where(ChannelVideoModel.channel_id == channel_id)
        )
        playlist_ids = await self.session.execute(
            select(ChannelPlaylistModel.playlist_id).where(ChannelPlaylistModel.channel_id == channel_id)
        )
        pids = [int(x) for x in playlist_ids.scalars().all()]
        item_ids: list[int] = []
        if pids:
            items = await self.session.execute(
                select(PlaylistItemModel.recording_id).where(PlaylistItemModel.playlist_id.in_(pids))
            )
            item_ids = [int(x) for x in items.scalars().all()]
        seen: set[int] = set()
        out: list[int] = []
        for rid in [int(x) for x in video_ids.scalars().all()] + item_ids:
            if rid not in seen:
                seen.add(rid)
                out.append(rid)
        return out
