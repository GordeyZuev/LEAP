"""Owner CRUD for playlists and public-link enable/disable/rotate."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.core.context import ServiceContext
from api.core.dependencies import get_service_context
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
from api.services.playlist_service import UNSET, PlaylistService, is_playable, item_unavailable_reason, poster_url_map
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
        duration += rec.final_duration or rec.duration or 0.0
    return len(items), duration


def _to_response(playlist: PlaylistModel) -> PlaylistResponse:
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
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
    )


def _first_playable_recording(playlist: PlaylistModel):
    for item in sorted(playlist.items or [], key=lambda i: i.position):
        rec = item.recording
        if rec is not None and is_playable(rec):
            return rec
    return None


def _to_list_item(playlist: PlaylistModel, poster_url: str | None = None) -> PlaylistListItem:
    video_count, duration_sum = _counts(playlist)
    return PlaylistListItem(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        video_count=video_count,
        duration_sum=duration_sum,
        share_enabled=playlist.share_enabled,
        poster_url=poster_url,
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
    )


def _to_item_response(item: PlaylistItemModel, poster_url: str | None = None) -> PlaylistItemResponse:
    rec = item.recording
    reason = item_unavailable_reason(rec) if rec else "deleted"
    return PlaylistItemResponse(
        id=item.id,
        recording_id=item.recording_id,
        position=item.position,
        display_name=rec.display_name if rec else "Unknown",
        start_time=rec.start_time if rec else item.created_at,
        duration=(rec.final_duration or rec.duration) if rec else 0.0,
        playable=is_playable(rec) if rec else False,
        unavailable_reason=reason,
        poster_url=poster_url,
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
    playlists = await svc.repo.list_by_user(ctx.user_id)
    if q and q.strip():
        needle = q.strip().lower()
        playlists = [p for p in playlists if needle in p.name.lower()]
    items, total, total_pages = paginate_list(playlists, page, per_page, sort_by, sort_order, PLAYLIST_SORT_FIELDS)
    first_recs = [_first_playable_recording(p) for p in items]
    posters = await poster_url_map(ctx.session, ctx.user_id, first_recs)
    return PlaylistListResponse(
        items=[
            _to_list_item(p, poster_url=posters.get(rec.id) if rec is not None else None)
            for p, rec in zip(items, first_recs, strict=True)
        ],
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


@router.get("/{playlist_id}", response_model=PlaylistResponse)
async def get_playlist(
    playlist_id: int,
    ctx: ServiceContext = Depends(get_service_context),
) -> PlaylistResponse:
    svc = PlaylistService(ctx.session, ctx.user_id)
    playlist = await svc.get_owned(playlist_id)
    return _to_response(playlist)


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
    return _to_response(playlist)


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
    posters = await poster_url_map(ctx.session, ctx.user_id, [i.recording for i in page_items])
    return PlaylistItemsResponse(
        items=[_to_item_response(i, poster_url=posters.get(i.recording_id)) for i in page_items],
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
    posters = await poster_url_map(ctx.session, ctx.user_id, [item.recording for item in playlist.items])
    by_id = {item.id: item for item in playlist.items}
    return [
        _to_item_response(by_id[item.id], poster_url=posters.get(by_id[item.id].recording_id))
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
