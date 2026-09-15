"""Owner CRUD for playlists and public-link enable/disable/rotate."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
from api.helpers.image_upload import presign_storage_keys, read_image_upload
from api.helpers.leap_publication import publication_looks_for_recordings
from api.helpers.media_duration import display_duration_seconds
from api.helpers.playlist_description import description_needs_item_titles, render_playlist_description
from api.schemas.common.pagination import paginate_list
from api.schemas.playlist import (
    PlaylistAddItemsRequest,
    PlaylistCreate,
    PlaylistItemResponse,
    PlaylistItemsResponse,
    PlaylistListItem,
    PlaylistListResponse,
    PlaylistReorderRequest,
    PlaylistResponse,
    PlaylistShareResponse,
    PlaylistUpdate,
)
from api.services.playlist_service import (
    UNSET,
    PlaylistService,
    is_playable,
    item_unavailable_reason,
    poster_preview_map,
)
from database.playlist_models import PlaylistItemModel, PlaylistModel
from logger import format_details, get_logger

router = APIRouter(prefix="/api/v1/playlists", tags=["Playlists"])
logger = get_logger()

PLAYLIST_SORT_FIELDS = {"created_at", "updated_at", "name"}


def _counts(playlist: PlaylistModel) -> tuple[int, float]:
    items = playlist.items or []
    duration = 0.0
    for item in items:
        rec = item.recording
        if rec is None:
            continue
        duration += display_duration_seconds(rec)
    return len(items), duration


def _to_response(
    playlist: PlaylistModel,
    *,
    poster_url: str | None = None,
    poster_asset_key: str | None = None,
) -> PlaylistResponse:
    video_count, duration_sum = _counts(playlist)
    return PlaylistResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        video_count=video_count,
        duration_sum=duration_sum,
        share_token=playlist.share_token,
        share_enabled=playlist.share_enabled,
        share_created_at=playlist.share_created_at,
        has_custom_cover=bool(playlist.cover_key),
        poster_url=poster_url,
        poster_asset_key=poster_asset_key or playlist.cover_key,
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
    )


def _first_playable_recording(playlist: PlaylistModel):
    """First lecture in course order (not blank/deleted). Auto cover uses this recording's poster."""
    for item in sorted(playlist.items or [], key=lambda i: i.position):
        rec = item.recording
        if rec is None or rec.deleted or rec.delete_state != "active" or rec.blank_record:
            continue
        return rec
    return None


def _to_list_item(
    playlist: PlaylistModel,
    poster_url: str | None = None,
    poster_asset_key: str | None = None,
    *,
    has_custom_cover: bool = False,
    item_titles: dict[int, str] | None = None,
    video_count: int | None = None,
    duration_sum: float | None = None,
    ordered_titles: list[str] | None = None,
) -> PlaylistListItem:
    if video_count is None or duration_sum is None:
        video_count, duration_sum = _counts(playlist)
    return PlaylistListItem(
        id=playlist.id,
        name=playlist.name,
        description=render_playlist_description(
            playlist.description,
            playlist,
            item_titles=item_titles,
            video_count=video_count,
            duration_sum=duration_sum,
            ordered_titles=ordered_titles,
        ),
        video_count=video_count,
        duration_sum=duration_sum,
        share_token=playlist.share_token,
        share_enabled=playlist.share_enabled,
        poster_url=poster_url,
        poster_asset_key=poster_asset_key,
        has_custom_cover=has_custom_cover,
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
    )


def _to_item_response(
    item: PlaylistItemModel,
    poster_url: str | None = None,
    poster_fallback_url: str | None = None,
    poster_asset_key: str | None = None,
    *,
    title: str | None = None,
) -> PlaylistItemResponse:
    rec = item.recording
    reason = item_unavailable_reason(rec) if rec else "deleted"
    display = rec.display_name if rec else "Unknown"
    return PlaylistItemResponse(
        id=item.id,
        recording_id=item.recording_id,
        position=item.position,
        display_name=display,
        title=title if title is not None else display,
        start_time=rec.start_time if rec else item.created_at,
        duration=display_duration_seconds(rec) if rec else 0.0,
        playable=is_playable(rec) if rec else False,
        unavailable_reason=reason,
        poster_url=poster_url,
        poster_fallback_url=poster_fallback_url,
        poster_asset_key=poster_asset_key,
        deleted=bool(rec.deleted) if rec else True,
        blank_record=bool(rec.blank_record) if rec else False,
    )


@router.get("", response_model=PlaylistListResponse)
async def list_playlists(
    q: str | None = Query(None, description="Search substring in playlist name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort_by: str = Query("updated_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistListResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    sort_field = sort_by if sort_by in PLAYLIST_SORT_FIELDS else "updated_at"
    playlists, total = await svc.repo.list_page(
        ctx.user_id,
        q=q,
        page=page,
        per_page=per_page,
        sort_by=sort_field,
        sort_order=sort_order,
    )
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    ids = [p.id for p in playlists]
    stats = await svc.repo.aggregate_stats(ids)
    first_by_id = await svc.repo.first_playable_recordings(ids)
    cover_urls = await presign_storage_keys([p.cover_key for p in playlists])
    recs_for_poster = [first_by_id[p.id] for p in playlists if not p.cover_key and p.id in first_by_id]
    looks = await publication_looks_for_recordings(ctx.session, ctx.user_id, recs_for_poster)
    previews = await poster_preview_map(ctx.session, ctx.user_id, recs_for_poster, looks=looks)
    jinja_ids = [p.id for p in playlists if description_needs_item_titles(p.description)]
    titles_by_pl = await svc.repo.item_titles_by_playlist(jinja_ids) if jinja_ids else {}
    out = []
    for p in playlists:
        video_count, duration_sum = stats.get(p.id, (0, 0.0))
        poster_url = None
        poster_asset_key = None
        if p.cover_key:
            poster_url = cover_urls.get(p.cover_key)
            poster_asset_key = p.cover_key
        else:
            rec = first_by_id.get(p.id)
            if rec is not None and rec.id in previews:
                poster_url = previews[rec.id].url
                poster_asset_key = previews[rec.id].asset_key or None
        ordered_titles = [name for _rid, name in titles_by_pl[p.id]] if p.id in titles_by_pl else None
        out.append(
            _to_list_item(
                p,
                poster_url=poster_url,
                poster_asset_key=poster_asset_key,
                has_custom_cover=bool(p.cover_key),
                video_count=video_count,
                duration_sum=duration_sum,
                ordered_titles=ordered_titles,
            )
        )
    return PlaylistListResponse(
        items=out,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.post("", response_model=PlaylistResponse, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    data: PlaylistCreate,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.create(data.name, data.description)
    await ctx.session.commit()
    await ctx.session.refresh(playlist)
    logger.info("Created playlist | {}", format_details(playlist=playlist.id))
    return _to_response(playlist)


async def _owner_cover_preview(playlist: PlaylistModel, ctx: ServiceContext) -> tuple[str | None, str | None]:
    if playlist.cover_key:
        urls = await presign_storage_keys([playlist.cover_key])
        return urls.get(playlist.cover_key), playlist.cover_key
    rec = _first_playable_recording(playlist)
    if rec is None:
        return None, None
    looks = await publication_looks_for_recordings(ctx.session, ctx.user_id, [rec])
    previews = await poster_preview_map(ctx.session, ctx.user_id, [rec], looks=looks)
    preview = previews.get(rec.id)
    if preview is None:
        return None, None
    return preview.url, preview.asset_key or None


@router.get("/{playlist_id}", response_model=PlaylistResponse)
async def get_playlist(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    poster_url, poster_asset_key = await _owner_cover_preview(playlist, ctx)
    return _to_response(playlist, poster_url=poster_url, poster_asset_key=poster_asset_key)


@router.patch("/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: int,
    data: PlaylistUpdate,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    dumped = data.model_dump(exclude_unset=True)
    playlist = await svc.update(
        playlist,
        name=dumped.get("name"),
        description=dumped.get("description", UNSET),
    )
    await ctx.session.commit()
    poster_url, poster_asset_key = await _owner_cover_preview(playlist, ctx)
    return _to_response(playlist, poster_url=poster_url, poster_asset_key=poster_asset_key)


@router.post("/{playlist_id}/cover", response_model=PlaylistResponse)
async def upload_playlist_cover(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
    file: UploadFile = File(...),
) -> PlaylistResponse:
    content, suffix = await read_image_upload(file)
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    await svc.set_cover(playlist, user_slug=ctx.user_slug, content=content, suffix=suffix)
    await ctx.session.commit()
    poster_url, poster_asset_key = await _owner_cover_preview(playlist, ctx)
    return _to_response(playlist, poster_url=poster_url, poster_asset_key=poster_asset_key)


@router.delete("/{playlist_id}/cover", response_model=PlaylistResponse)
async def delete_playlist_cover(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    await svc.clear_cover(playlist)
    await ctx.session.commit()
    playlist = await svc.get_owned(playlist_id)
    poster_url, poster_asset_key = await _owner_cover_preview(playlist, ctx)
    return _to_response(playlist, poster_url=poster_url, poster_asset_key=poster_asset_key)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    await svc.delete(playlist)
    await ctx.session.commit()
    logger.info("Deleted playlist | {}", format_details(playlist=playlist_id))


@router.get("/{playlist_id}/items", response_model=PlaylistItemsResponse)
async def list_playlist_items(
    playlist_id: int,
    q: str | None = Query(None),
    from_date: str | None = Query(None, description="Filter: recording start_time >= from_date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="Filter: recording start_time <= to_date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=200),
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistItemsResponse:
    from_dt = None
    to_dt = None
    if from_date:
        from utils.date_utils import InvalidDateFormatError, parse_from_date_to_datetime

        try:
            from_dt = parse_from_date_to_datetime(from_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if to_date:
        from utils.date_utils import InvalidDateFormatError, parse_to_date_to_datetime

        try:
            to_dt = parse_to_date_to_datetime(to_date)
        except InvalidDateFormatError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    svc = PlaylistService(ctx.session, ctx.user_id)
    await svc.get_owned(playlist_id)
    items = await svc.repo.list_items(playlist_id, q=q, from_date=from_dt, to_date=to_dt)
    page_items, total, total_pages = paginate_list(
        items, page, per_page, sort_by="position", sort_order="asc", allowed_sort_fields={"position"}
    )
    recs = [i.recording for i in page_items]
    looks = await publication_looks_for_recordings(ctx.session, ctx.user_id, recs)
    previews = await poster_preview_map(ctx.session, ctx.user_id, recs, looks=looks)
    return PlaylistItemsResponse(
        items=[
            _to_item_response(
                i,
                poster_url=previews[i.recording_id].url if i.recording_id in previews else None,
                poster_fallback_url=previews[i.recording_id].fallback_url if i.recording_id in previews else None,
                poster_asset_key=previews[i.recording_id].asset_key or None if i.recording_id in previews else None,
                title=looks[i.recording_id].title if i.recording_id in looks else None,
            )
            for i in page_items
        ],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.post("/{playlist_id}/items", response_model=list[PlaylistItemResponse], status_code=status.HTTP_201_CREATED)
async def add_playlist_items(
    playlist_id: int,
    data: PlaylistAddItemsRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> list[PlaylistItemResponse]:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    created = await svc.add_items(playlist, data.recording_ids)
    await ctx.session.commit()
    # Reload to get recording relationships
    playlist = await svc.get_owned(playlist_id)
    recs = [item.recording for item in playlist.items]
    looks = await publication_looks_for_recordings(ctx.session, ctx.user_id, recs)
    previews = await poster_preview_map(ctx.session, ctx.user_id, recs, looks=looks)
    by_id = {item.id: item for item in playlist.items}
    return [
        _to_item_response(
            by_id[item.id],
            poster_url=previews[by_id[item.id].recording_id].url if by_id[item.id].recording_id in previews else None,
            poster_fallback_url=previews[by_id[item.id].recording_id].fallback_url
            if by_id[item.id].recording_id in previews
            else None,
            poster_asset_key=previews[by_id[item.id].recording_id].asset_key or None
            if by_id[item.id].recording_id in previews
            else None,
            title=looks[by_id[item.id].recording_id].title if by_id[item.id].recording_id in looks else None,
        )
        for item in created
        if item.id in by_id
    ]


@router.delete("/{playlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist_item(
    playlist_id: int,
    item_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    await svc.remove_item(playlist, item_id)
    await ctx.session.commit()


@router.put("/{playlist_id}/items/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_playlist_items(
    playlist_id: int,
    data: PlaylistReorderRequest,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    await svc.reorder(playlist, data.item_ids)
    await ctx.session.commit()


@router.post("/{playlist_id}/share", response_model=PlaylistShareResponse)
async def enable_playlist_share(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistShareResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    playlist = await svc.enable_share(playlist)
    await ctx.session.commit()
    if playlist.share_token is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create share link")
    return PlaylistShareResponse(share_token=playlist.share_token, share_enabled=True)


@router.delete("/{playlist_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def disable_playlist_share(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> None:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    await svc.disable_share(playlist)
    await ctx.session.commit()


@router.post("/{playlist_id}/share/rotate", response_model=PlaylistShareResponse)
async def rotate_playlist_share(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistShareResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    playlist = await svc.rotate_share(playlist)
    await ctx.session.commit()
    if playlist.share_token is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to rotate share link")
    return PlaylistShareResponse(share_token=playlist.share_token, share_enabled=True)


@router.get("/{playlist_id}/channels")
async def list_playlist_channels(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
):
    from api.repositories.channel_repo import ChannelRepository
    from api.schemas.channel import ChannelSummary

    svc = PlaylistService(ctx.session, ctx.user_id)
    await svc.get_owned(playlist_id)
    rows = await ChannelRepository(ctx.session).summaries_for_playlist(playlist_id, ctx.user_id)
    return [ChannelSummary(id=ch.id, name=ch.name, slug=ch.slug, membership_id=mid) for ch, mid in rows]


@router.get("/{playlist_id}/share/analytics")
async def get_playlist_share_analytics(
    playlist_id: int,
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

    svc = PlaylistService(ctx.session, ctx.user_id)
    await svc.get_owned(playlist_id)
    if not from_date or not to_date:
        from_date, to_date = default_analytics_range()
    try:
        start_d, end_d, start_dt, end_dt = parse_analytics_range(from_date, to_date)
    except AnalyticsRangeError as exc:
        raise analytics_range_http_error(exc) from exc
    items = await svc.repo.list_items(playlist_id)
    recording_ids = [i.recording_id for i in items]
    return await build_catalog_analytics(
        ctx.session,
        recording_ids=recording_ids,
        from_date=start_d,
        to_date=end_d,
        from_dt=start_dt,
        to_dt=end_dt,
        owner_user_id=ctx.user_id,
        playlist_id=playlist_id,
    )
