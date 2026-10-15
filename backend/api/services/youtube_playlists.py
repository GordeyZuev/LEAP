"""YouTube playlist operations using a user's stored YouTube credential."""

import asyncio
import json
from typing import Any

from fastapi import HTTPException, status
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.auth_repos import UserCredentialRepository
from logger import get_logger
from video_upload_module.config_factory import YouTubeUploadConfig
from video_upload_module.platforms.youtube.playlist_manager import YouTubePlaylistManager
from video_upload_module.platforms.youtube.token_handler import TokenRefreshError
from video_upload_module.uploader_factory import create_youtube_uploader_from_db

logger = get_logger()
YOUTUBE_PLAYLIST_SEARCH_TIMEOUT_SECONDS = 25


def _playlist(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet") or {}
    details = item.get("contentDetails") or {}
    status_data = item.get("status") or {}
    playlist_id = str(item.get("id", ""))
    return {
        "id": playlist_id,
        "title": str(snippet.get("title") or ""),
        "description": str(snippet.get("description") or ""),
        "privacy_status": status_data.get("privacyStatus", "private"),
        "item_count": int(details.get("itemCount") or 0),
        "url": f"https://www.youtube.com/playlist?list={playlist_id}",
    }


def _raise_youtube_error(exc: HttpError) -> HTTPException:
    code = getattr(exc.resp, "status", None)
    payload = getattr(exc, "content", b"")
    message = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    try:
        response_body = json.loads(message)
        reasons = " ".join(
            str(row.get("reason", "")) for row in response_body.get("error", {}).get("errors", [])
        ).casefold()
    except (json.JSONDecodeError, AttributeError, TypeError):
        reasons = message.casefold()
    if code == 401 or (code == 403 and "insufficientpermissions" in reasons):
        return HTTPException(
            # Keep provider OAuth failures distinct from LEAP session expiry.
            # The frontend refreshes its own session for every HTTP 401.
            status_code=status.HTTP_403_FORBIDDEN,
            detail="YouTube permissions are missing or expired. Reconnect this account in Credentials.",
        )
    if code == 403 and ("quota" in reasons or "dailylimit" in reasons):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="YouTube API quota exceeded")
    if code == 403 and "accessnotconfigured" in reasons:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube Data API v3 is not enabled for this application. Contact your administrator.",
        )
    if code == 404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="YouTube playlist not found")
    if code == 400:
        if "maxplaylistexceeded" in reasons:
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="This channel has reached YouTube's playlist limit"
            )
        if "playlistoperationunsupported" in reasons:
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This YouTube playlist cannot be modified"
            )
        if "playlisttitlerequired" in reasons or "invalidplaylistsnippet" in reasons:
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="YouTube rejected the playlist title or description",
            )
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YouTube rejected the playlist request")
    if code in (403, 429):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="YouTube denied this playlist operation")
    logger.warning(f"YouTube playlist API error | status={code}")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="YouTube API is temporarily unavailable")


async def get_playlist_manager(credential_id: int, user_id: str, session: AsyncSession) -> YouTubePlaylistManager:
    """Validate ownership and authenticate the uploader for playlist management."""
    repository = UserCredentialRepository(session)
    credential = await repository.get_by_id(credential_id, user_id)
    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="YouTube credential not found")
    if credential.platform != "youtube":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Credential is not for YouTube")
    if not credential.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YouTube credential is inactive")

    uploader = await create_youtube_uploader_from_db(
        credential_id,
        session,
        user_id,
        YouTubeUploadConfig(enabled=True),
    )
    try:
        authenticated = await uploader.authenticate()
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="YouTube authorization timed out. Try again.",
        ) from exc
    if not authenticated:
        await repository.set_needs_reauth(credential_id, True, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="YouTube authorization failed. Reconnect this account in Credentials.",
        )
    return YouTubePlaylistManager(
        service=uploader.service,
        config=uploader.config,
        credentials=uploader.credentials,
        credential_provider=uploader.credential_provider,
    )


async def map_youtube_playlist_error(
    exc: Exception,
    credential_id: int,
    user_id: str,
    session: AsyncSession,
) -> HTTPException:
    """Map provider auth failures and mark credentials that need reconnecting."""
    if isinstance(exc, TimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="YouTube API request timed out. Try again.",
        )
    if isinstance(exc, TokenRefreshError):
        response = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="YouTube authorization expired. Reconnect this account in Credentials.",
        )
    elif isinstance(exc, HttpError):
        response = _raise_youtube_error(exc)
    else:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="YouTube API is temporarily unavailable")
    if response.status_code == status.HTTP_403_FORBIDDEN and "reconnect this account" in response.detail.casefold():
        await UserCredentialRepository(session).set_needs_reauth(credential_id, True, user_id=user_id)
    return response


async def list_playlists(manager: YouTubePlaylistManager, query: str | None, page_token: str | None) -> dict[str, Any]:
    """List playlists; a text query scans all provider pages to search the full channel."""
    normalized_query = (query or "").strip().casefold()
    if not normalized_query:
        response = await manager.list_playlists(page_token=page_token)
        items = [_playlist(item) for item in response.get("items", [])]
        return {
            "items": items,
            "next_page_token": response.get("nextPageToken"),
            "total": int(response.get("pageInfo", {}).get("totalResults", len(items))),
        }

    matches: list[dict[str, Any]] = []
    next_token: str | None = None
    try:
        async with asyncio.timeout(YOUTUBE_PLAYLIST_SEARCH_TIMEOUT_SECONDS):
            while True:
                response = await manager.list_playlists(page_token=next_token)
                for raw_item in response.get("items", []):
                    item = _playlist(raw_item)
                    if (
                        normalized_query in item["title"].casefold()
                        or normalized_query in item["description"].casefold()
                    ):
                        matches.append(item)
                next_token = response.get("nextPageToken")
                if not next_token:
                    break
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="YouTube playlist search took too long. Try again.",
        ) from exc
    return {"items": matches, "next_page_token": None, "total": len(matches)}


async def get_playlist(manager: YouTubePlaylistManager, playlist_id: str) -> dict[str, Any]:
    item = await manager.get_playlist_record(playlist_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="YouTube playlist not found")
    return _playlist(item)
