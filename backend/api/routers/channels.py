"""Owner CRUD for channels and public catalog by slug."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
from api.dependencies import get_db_session
from api.helpers.catalog_blurb import excerpt, recording_catalog_blurb
from api.helpers.channel_description import render_channel_description
from api.helpers.image_upload import presign_storage_keys, read_image_upload
from api.helpers.leap_publication import publication_looks_for_recordings
from api.helpers.media_duration import display_duration_seconds
from api.helpers.playlist_description import render_playlist_description
from api.repositories.channel_repo import ChannelRepository
from api.repositories.playlist_repo import PlaylistRepository
from api.schemas.channel import (
    ChannelAddIdsRequest,
    ChannelCreate,
    ChannelListItem,
    ChannelListResponse,
    ChannelPlaylistRow,
    ChannelReorderRequest,
    ChannelResponse,
    ChannelShareResponse,
    ChannelUpdate,
    ChannelVideoRow,
    PublicChannelPlaylist,
    PublicChannelResponse,
    PublicChannelVideo,
)
from api.schemas.common.pagination import paginate_list
from api.services.channel_service import UNSET, ChannelService
from api.services.playlist_service import is_playable, item_unavailable_reason, poster_preview_map
from database.channel_models import ChannelModel
from logger import format_details, get_logger

router = APIRouter(tags=["Channels"])
logger = get_logger()
CHANNEL_SORT_FIELDS = {"created_at", "updated_at", "name", "slug"}


def _hidden_video_reason(*, share_enabled: bool, playable: bool, rec_reason: str | None) -> str | None:
    if not share_enabled:
        return "Share off"
    if not playable:
        return "Not ready" if rec_reason in {None, "not_ready"} else rec_reason.replace("_", " ").title()
    return None


async def _banner_url(channel: ChannelModel) -> str | None:
    if not channel.banner_key:
        return None
    urls = await presign_storage_keys([channel.banner_key])
    return urls.get(channel.banner_key)


async def _to_channel_response(channel: ChannelModel, repo: ChannelRepository) -> ChannelResponse:
    counts = await repo.membership_counts([channel.id])
    videos, playlists = counts.get(channel.id, (0, 0))
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        slug=channel.slug,
        description=channel.description,
        share_enabled=channel.share_enabled,
        video_count=videos,
        playlist_count=playlists,
        banner_url=await _banner_url(channel),
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


@router.get("/api/v1/channels", response_model=ChannelListResponse)
async def list_channels(
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort_by: str = Query("updated_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    ctx: ServiceContext = Depends(get_service_context),
) -> ChannelListResponse:
    svc = ChannelService(ctx.session, ctx.user_id)
    sort_field = sort_by if sort_by in CHANNEL_SORT_FIELDS else "updated_at"
    channels, total = await svc.repo.list_page(
        ctx.user_id, q=q, page=page, per_page=per_page, sort_by=sort_field, sort_order=sort_order
    )
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    ids = [c.id for c in channels]
    counts = await svc.repo.membership_counts(ids)
    banners = await presign_storage_keys([c.banner_key for c in channels])
    return ChannelListResponse(
        items=[
            ChannelListItem(
                id=c.id,
                name=c.name,
                slug=c.slug,
                description=c.description,
                share_enabled=c.share_enabled,
                video_count=counts.get(c.id, (0, 0))[0],
                playlist_count=counts.get(c.id, (0, 0))[1],
                banner_url=banners.get(c.banner_key) if c.banner_key else None,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in channels
        ],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.post("/api/v1/channels", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: ChannelCreate,
    ctx: ServiceContext = Depends(get_service_context),
) -> ChannelResponse:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.create(data.name, slug=data.slug, description=data.description)
    await ctx.session.commit()
    await ctx.session.refresh(channel)
    logger.info("Created channel | {}", format_details(channel=channel.id))
    return await _to_channel_response(channel, svc.repo)


@router.get("/api/v1/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ChannelResponse:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    return await _to_channel_response(channel, svc.repo)


@router.patch("/api/v1/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    data: ChannelUpdate,
    ctx: ServiceContext = Depends(get_service_context),
) -> ChannelResponse:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    dumped = data.model_dump(exclude_unset=True)
    channel = await svc.update(
        channel,
        name=dumped.get("name"),
        slug=dumped.get("slug"),
        description=dumped.get("description", UNSET),
    )
    await ctx.session.commit()
    return await _to_channel_response(channel, svc.repo)


@router.delete("/api/v1/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.delete(channel)
    await ctx.session.commit()


@router.post("/api/v1/channels/{channel_id}/banner", response_model=ChannelResponse)
async def upload_channel_banner(
    channel_id: int,
    ctx: ServiceContext = Depends(get_service_context),
    file: UploadFile = File(...),
) -> ChannelResponse:
    content, suffix = await read_image_upload(file)
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.set_banner(channel, user_slug=ctx.user_slug, content=content, suffix=suffix)
    await ctx.session.commit()
    return await _to_channel_response(channel, svc.repo)


@router.delete("/api/v1/channels/{channel_id}/banner", response_model=ChannelResponse)
async def delete_channel_banner(
    channel_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ChannelResponse:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.clear_banner(channel)
    await ctx.session.commit()
    return await _to_channel_response(channel, svc.repo)


@router.post("/api/v1/channels/{channel_id}/share", response_model=ChannelShareResponse)
async def enable_channel_share(
    channel_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> ChannelShareResponse:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    channel = await svc.enable_share(channel)
    await ctx.session.commit()
    return ChannelShareResponse(slug=channel.slug, share_enabled=True)


@router.delete("/api/v1/channels/{channel_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def disable_channel_share(
    channel_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.disable_share(channel)
    await ctx.session.commit()


@router.get("/api/v1/channels/{channel_id}/videos")
async def list_channel_videos(
    channel_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=200),
    ctx: ServiceContext = Depends(get_service_context),
):
    svc = ChannelService(ctx.session, ctx.user_id)
    await svc.get_owned(channel_id)
    rows = await svc.repo.list_videos(channel_id)
    recs = [row.recording for row in rows if row.recording is not None]
    looks = await publication_looks_for_recordings(ctx.session, ctx.user_id, recs)
    previews = await poster_preview_map(ctx.session, ctx.user_id, recs, looks=looks)
    items: list[ChannelVideoRow] = []
    for row in rows:
        rec = row.recording
        playable = is_playable(rec) if rec else False
        share_on = bool(rec and rec.share_enabled and rec.share_token)
        reason = _hidden_video_reason(
            share_enabled=share_on,
            playable=playable,
            rec_reason=item_unavailable_reason(rec) if rec else "deleted",
        )
        title = looks[rec.id].title if rec and rec.id in looks else (rec.display_name if rec else "Unknown")
        preview = previews.get(rec.id) if rec else None
        token = str(rec.share_token) if rec and rec.share_token else None
        items.append(
            ChannelVideoRow(
                recording_id=row.recording_id,
                position=row.position,
                title=title,
                start_time=rec.start_time if rec else None,
                duration=display_duration_seconds(rec) if rec else 0.0,
                share_enabled=share_on,
                playable=playable,
                public_visible=share_on and playable,
                hidden_reason=reason,
                poster_url=preview.url if preview else None,
                poster_asset_key=preview.asset_key if preview else None,
                share_token=token,
            )
        )
    page_items, total, total_pages = paginate_list(
        items, page, per_page, sort_by="position", sort_order="asc", allowed_sort_fields={"position"}
    )
    return {"items": page_items, "page": page, "per_page": per_page, "total": total, "total_pages": total_pages}


@router.post("/api/v1/channels/{channel_id}/videos", status_code=status.HTTP_201_CREATED)
async def add_channel_videos(
    channel_id: int,
    data: ChannelAddIdsRequest,
    ctx: ServiceContext = Depends(get_service_context),
):
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    created = await svc.add_videos(channel, data.ids)
    await ctx.session.commit()
    return {"added": len(created)}


@router.delete("/api/v1/channels/{channel_id}/videos/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_video(
    channel_id: int,
    recording_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.remove_video(channel, recording_id)
    await ctx.session.commit()


@router.put("/api/v1/channels/{channel_id}/videos/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_channel_videos(
    channel_id: int,
    data: ChannelReorderRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.reorder_videos(channel, data.ids)
    await ctx.session.commit()


@router.get("/api/v1/channels/{channel_id}/playlists")
async def list_channel_playlists_endpoint(
    channel_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=200),
    ctx: ServiceContext = Depends(get_service_context),
):
    svc = ChannelService(ctx.session, ctx.user_id)
    await svc.get_owned(channel_id)
    rows = await svc.repo.list_channel_playlists(channel_id)
    playlist_ids = [row.playlist_id for row in rows]
    pl_repo = PlaylistRepository(ctx.session)
    stats = await pl_repo.aggregate_stats(playlist_ids)
    first_by_id = await pl_repo.first_playable_recordings(playlist_ids)
    cover_urls = await presign_storage_keys([row.playlist.cover_key if row.playlist else None for row in rows])
    recs = [first_by_id[pid] for pid in playlist_ids if pid in first_by_id]
    looks = await publication_looks_for_recordings(ctx.session, ctx.user_id, recs)
    previews = await poster_preview_map(ctx.session, ctx.user_id, recs, looks=looks)
    items: list[ChannelPlaylistRow] = []
    for row in rows:
        pl = row.playlist
        share_on = bool(pl and pl.share_enabled and pl.share_token)
        video_count, duration_sum = stats.get(row.playlist_id, (0, 0.0))
        poster_url = None
        poster_asset_key = None
        cover_key = pl.cover_key if pl else None
        if cover_key:
            poster_url = cover_urls.get(cover_key)
            poster_asset_key = cover_key
        else:
            rec = first_by_id.get(row.playlist_id)
            if rec is not None and rec.id in previews:
                poster_url = previews[rec.id].url
                poster_asset_key = previews[rec.id].asset_key or None
        token = str(pl.share_token) if pl and pl.share_token else None
        items.append(
            ChannelPlaylistRow(
                playlist_id=row.playlist_id,
                position=row.position,
                name=pl.name if pl else "Unknown",
                video_count=video_count,
                duration_sum=duration_sum,
                share_enabled=share_on,
                public_visible=share_on,
                hidden_reason=None if share_on else "Share off",
                poster_url=poster_url,
                poster_asset_key=poster_asset_key,
                share_token=token,
                has_custom_cover=bool(cover_key),
            )
        )
    page_items, total, total_pages = paginate_list(
        items, page, per_page, sort_by="position", sort_order="asc", allowed_sort_fields={"position"}
    )
    return {"items": page_items, "page": page, "per_page": per_page, "total": total, "total_pages": total_pages}


@router.post("/api/v1/channels/{channel_id}/playlists", status_code=status.HTTP_201_CREATED)
async def add_channel_playlists(
    channel_id: int,
    data: ChannelAddIdsRequest,
    ctx: ServiceContext = Depends(get_service_context),
):
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    created = await svc.add_playlists(channel, data.ids)
    await ctx.session.commit()
    return {"added": len(created)}


@router.delete("/api/v1/channels/{channel_id}/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_playlist(
    channel_id: int,
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.remove_playlist(channel, playlist_id)
    await ctx.session.commit()


@router.put("/api/v1/channels/{channel_id}/playlists/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_channel_playlists(
    channel_id: int,
    data: ChannelReorderRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = ChannelService(ctx.session, ctx.user_id)
    channel = await svc.get_owned(channel_id)
    await svc.reorder_playlists(channel, data.ids)
    await ctx.session.commit()


async def _public_channel_order_page(
    channel: ChannelModel,
    *,
    kind: Literal["videos", "playlists"],
    page: int,
    per_page: int,
    session: AsyncSession,
    repo: ChannelRepository,
) -> PublicChannelResponse:
    """Use SQL paging for the default catalog view without loading both membership lists."""
    videos_total = await repo.public_video_count(channel.id)
    playlists_total = await repo.public_playlist_count(channel.id)
    total = videos_total if kind == "videos" else playlists_total
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = min(page, total_pages)
    banner_url = await _banner_url(channel)
    videos: list[PublicChannelVideo] = []
    playlists: list[PublicChannelPlaylist] = []

    if kind == "videos":
        rows = await repo.public_videos_page(channel.id, page=current_page, per_page=per_page)
        recs = [rec for _membership, rec in rows]
        looks = await publication_looks_for_recordings(session, channel.user_id, recs)
        previews = await poster_preview_map(session, channel.user_id, recs, looks=looks)
        videos = [
            PublicChannelVideo(
                title=rec.display_name,
                duration=display_duration_seconds(rec),
                start_time=rec.start_time,
                poster_url=previews[rec.id].url if rec.id in previews else None,
                poster_asset_key=previews[rec.id].asset_key if rec.id in previews else None,
                share_token=str(rec.share_token),
                blurb=recording_catalog_blurb(rec),
            )
            for _membership, rec in rows
        ]
    else:
        rows = await repo.public_playlists_page(channel.id, page=current_page, per_page=per_page)
        playlist_ids = [pl.id for _membership, pl in rows]
        playlist_repo = PlaylistRepository(session)
        stats = await playlist_repo.aggregate_stats(playlist_ids)
        first = await playlist_repo.first_playable_recordings(playlist_ids)
        recs = list(first.values())
        looks = await publication_looks_for_recordings(session, channel.user_id, recs)
        previews = await poster_preview_map(session, channel.user_id, recs, looks=looks)
        covers = await presign_storage_keys([pl.cover_key for _membership, pl in rows])
        for _membership, pl in rows:
            video_count, duration_sum = stats.get(pl.id, (0, 0.0))
            first_rec = first.get(pl.id)
            preview = previews.get(first_rec.id) if first_rec else None
            playlists.append(
                PublicChannelPlaylist(
                    name=pl.name,
                    video_count=video_count,
                    duration_sum=duration_sum,
                    poster_url=covers.get(pl.cover_key) if pl.cover_key else (preview.url if preview else None),
                    poster_asset_key=pl.cover_key if pl.cover_key else (preview.asset_key if preview else None),
                    share_token=str(pl.share_token),
                    blurb=excerpt(
                        render_playlist_description(
                            pl.description,
                            video_count=video_count,
                            duration_sum=duration_sum,
                            ordered_titles=[],
                        )
                    ),
                )
            )

    return PublicChannelResponse(
        name=channel.name,
        slug=channel.slug,
        description=None,
        banner_url=banner_url,
        videos=videos,
        playlists=playlists,
        kind=kind,
        page=current_page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        videos_total=videos_total,
        playlists_total=playlists_total,
    )


@router.get("/api/v1/c/{slug}", response_model=PublicChannelResponse)
async def get_public_channel(
    slug: str,
    kind: Literal["all", "videos", "playlists"] = Query("all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=60),
    q: str | None = Query(None, max_length=120),
    sort: Literal["order", "newest", "oldest", "name", "duration", "videos"] = Query("order"),
    session: AsyncSession = Depends(get_db_session),
) -> PublicChannelResponse:
    svc = ChannelService(session, user_id="")
    channel = await svc.require_public(slug)
    if kind != "all" and sort == "order" and not (q or "").strip() and not channel.description:
        return await _public_channel_order_page(
            channel, kind=kind, page=page, per_page=per_page, session=session, repo=svc.repo
        )
    # AsyncSession is not safe for concurrent statements on the same connection.
    video_rows = await svc.repo.public_videos(channel.id)
    playlist_rows = await svc.repo.public_playlists(channel.id)
    banner_url = await _banner_url(channel)
    recs = [rec for _row, rec in video_rows]
    pl_ids = [pl.id for _row, pl in playlist_rows]
    pl_repo = PlaylistRepository(session)
    stats = await pl_repo.aggregate_stats(pl_ids)
    all_video_count = len(recs)
    all_playlist_count = len(playlist_rows)
    all_video_titles = [rec.display_name for rec in recs]
    all_playlist_names = [pl.name for _row, pl in playlist_rows]
    all_video_duration = sum(display_duration_seconds(rec) for rec in recs)
    videos = []
    for _row, rec in video_rows:
        if rec.share_token is None:
            continue
        videos.append(
            PublicChannelVideo(
                title=rec.display_name,
                duration=display_duration_seconds(rec),
                start_time=rec.start_time,
                poster_url=None,
                poster_asset_key=None,
                share_token=str(rec.share_token),
                blurb=recording_catalog_blurb(rec),
            )
        )
    playlists = []
    for _row, pl in playlist_rows:
        if pl.share_token is None:
            continue
        video_count, duration_sum = stats.get(pl.id, (0, 0.0))
        playlists.append(
            PublicChannelPlaylist(
                name=pl.name,
                video_count=video_count,
                duration_sum=duration_sum,
                poster_url=None,
                poster_asset_key=pl.cover_key,
                share_token=str(pl.share_token),
                blurb=excerpt(
                    render_playlist_description(
                        pl.description,
                        video_count=video_count,
                        duration_sum=duration_sum,
                        ordered_titles=[],
                    )
                ),
            )
        )

    description = render_channel_description(
        channel.description,
        video_count=all_video_count,
        playlist_count=all_playlist_count,
        duration_sum=all_video_duration,
        video_titles=all_video_titles,
        playlist_names=all_playlist_names,
    )
    videos_total_all = len(videos)
    playlists_total_all = len(playlists)

    needle = (q or "").strip().casefold()
    if kind == "videos":
        if needle:
            videos = [v for v in videos if needle in v.title.casefold() or needle in (v.blurb or "").casefold()]
        if sort == "newest":
            videos.sort(key=lambda v: v.start_time or datetime.min.replace(tzinfo=UTC), reverse=True)
        elif sort == "oldest":
            videos.sort(key=lambda v: (v.start_time is None, v.start_time or datetime.max.replace(tzinfo=UTC)))
        elif sort == "name":
            videos.sort(key=lambda v: v.title.casefold())
        elif sort == "duration":
            videos.sort(key=lambda v: v.duration, reverse=True)
    elif kind == "playlists":
        if needle:
            playlists = [p for p in playlists if needle in p.name.casefold() or needle in (p.blurb or "").casefold()]
        if sort == "name":
            playlists.sort(key=lambda p: p.name.casefold())
        elif sort == "videos":
            playlists.sort(key=lambda p: p.video_count, reverse=True)
        elif sort == "duration":
            playlists.sort(key=lambda p: p.duration_sum, reverse=True)

    if kind == "all":
        page_videos, page_playlists = videos, playlists
        total = len(videos) + len(playlists)
        total_pages = 1
    else:
        active = videos if kind == "videos" else playlists
        total = len(active)
        total_pages = max(1, (total + per_page - 1) // per_page)
        offset = (min(page, total_pages) - 1) * per_page
        active_page = active[offset : offset + per_page]
        page_videos = active_page if kind == "videos" else []
        page_playlists = active_page if kind == "playlists" else []

    page_video_tokens = {v.share_token for v in page_videos}
    page_playlist_tokens = {p.share_token for p in page_playlists}
    selected_video_recs = [rec for _row, rec in video_rows if str(rec.share_token) in page_video_tokens]
    selected_playlist_rows = [(_row, pl) for _row, pl in playlist_rows if str(pl.share_token) in page_playlist_tokens]
    selected_playlist_ids = [pl.id for _row, pl in selected_playlist_rows]
    selected_first = await pl_repo.first_playable_recordings(selected_playlist_ids)
    poster_recs = [*selected_video_recs, *selected_first.values()]
    looks = await publication_looks_for_recordings(session, channel.user_id, poster_recs)
    previews = await poster_preview_map(session, channel.user_id, poster_recs, looks=looks)
    cover_page_urls = await presign_storage_keys([pl.cover_key for _row, pl in selected_playlist_rows])
    video_preview_by_token = {str(rec.share_token): previews.get(rec.id) for rec in selected_video_recs}
    for video in page_videos:
        preview = video_preview_by_token.get(video.share_token)
        video.poster_url = preview.url if preview else None
        video.poster_asset_key = preview.asset_key if preview else None
    first_by_playlist = selected_first
    for playlist in page_playlists:
        match = next((pl for _row, pl in selected_playlist_rows if str(pl.share_token) == playlist.share_token), None)
        if match is None:
            continue
        if match.cover_key:
            playlist.poster_url = cover_page_urls.get(match.cover_key)
        else:
            rec = first_by_playlist.get(match.id)
            preview = previews.get(rec.id) if rec else None
            playlist.poster_url = preview.url if preview else None
            playlist.poster_asset_key = (preview.asset_key or None) if preview else None

    return PublicChannelResponse(
        name=channel.name,
        slug=channel.slug,
        description=description,
        banner_url=banner_url,
        videos=page_videos,
        playlists=page_playlists,
        kind=kind,
        page=min(page, total_pages),
        per_page=per_page if kind != "all" else total,
        total=total,
        total_pages=total_pages,
        videos_total=videos_total_all,
        playlists_total=playlists_total_all,
    )


@router.get("/api/v1/channels/{channel_id}/share/analytics")
async def get_channel_share_analytics(
    channel_id: int,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    ctx: ServiceContext = Depends(get_service_context),
):
    from api.services.analytics_service import (
        AnalyticsRangeError,
        analytics_range_http_error,
        default_analytics_range,
        parse_analytics_range,
    )
    from api.services.share_observability import build_catalog_analytics

    svc = ChannelService(ctx.session, ctx.user_id)
    await svc.get_owned(channel_id)
    if not from_date or not to_date:
        from_date, to_date = default_analytics_range()
    try:
        start_d, end_d, start_dt, end_dt = parse_analytics_range(from_date, to_date)
    except AnalyticsRangeError as exc:
        raise analytics_range_http_error(exc) from exc
    recording_ids = await svc.repo.recording_ids_in_channel_scope(channel_id)
    return await build_catalog_analytics(
        ctx.session,
        recording_ids=recording_ids,
        from_date=start_d,
        to_date=end_d,
        from_dt=start_dt,
        to_dt=end_dt,
        owner_user_id=ctx.user_id,
        channel_id=channel_id,
    )


@router.post("/api/v1/c/{slug}/beacon", status_code=status.HTTP_204_NO_CONTENT)
async def public_channel_beacon(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    from api.services.share_observability import ShareObservabilityService

    svc = ChannelService(session, user_id="")
    try:
        channel = await svc.require_public(slug)
    except HTTPException:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        await ShareObservabilityService().record_surface_view(
            owner_user_id=channel.user_id, request=request, channel_id=channel.id
        )
    except Exception as exc:
        logger.info("channel beacon failed (ignored): {!r}", exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/c/{slug}/engagement", status_code=status.HTTP_204_NO_CONTENT)
async def public_channel_engagement(
    slug: str,
    request: Request,
) -> Response:
    """Reserved for future channel-surface engagement; MVP returns 204 without persisting."""
    from api.services.share_engagement import MAX_BODY_BYTES

    _ = slug
    if len(await request.body()) > MAX_BODY_BYTES:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
