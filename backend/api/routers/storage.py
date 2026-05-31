"""Internal endpoint that streams files from the storage backend.

This exists primarily for the LOCAL backend, where ``StorageBackend.presigned_url``
returns ``/api/v1/storage/stream?key=...`` instead of an externally signed URL.
The endpoint authenticates the user, verifies they own the key (multi-tenancy),
then streams the object through the API.

For the S3 backend in production, frontends use real presigned URLs and skip
this endpoint entirely — but it's kept available for thumbnails and small
artifacts that callers prefer to fetch via the API.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from api.auth.dependencies import get_current_user
from api.schemas.auth import UserInDB
from file_storage.factory import get_storage_backend
from logger import get_logger

logger = get_logger()
router = APIRouter(prefix="/api/v1/storage", tags=["Storage"])


def _is_user_key(key: str, user_slug: int) -> bool:
    """Check whether the key belongs to ``user_slug`` (multi-tenancy guard).

    Accepts:
      - ``users/000123/...`` — user's own files
      - ``shared/...`` — shared/global assets readable by any user (thumbnails)
    """
    expected_prefix = f"users/user_{user_slug:06d}/"
    return key.startswith((expected_prefix, "shared/"))


@router.get("/stream")
async def stream_storage_object(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    key: str = Query(..., description="Storage key relative to the backend root"),
) -> StreamingResponse:
    """Stream a stored object after verifying access.

    Returns ``404`` if the object is missing, ``403`` for cross-tenant access.
    """
    # Path traversal guard
    if ".." in key.split("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key")

    if not _is_user_key(key, current_user.user_slug):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    storage = get_storage_backend()
    if not await storage.exists(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Inline-loading is fine: this endpoint is intended for thumbnails / small
    # artifacts only. Large videos go through real presigned URLs in production.
    content = await storage.load(key)
    # Best-effort content type by suffix; client can override.
    suffix = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    media_type = {
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
        "mkv": "video/x-matroska",
        "mp3": "audio/mpeg",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "json": "application/json",
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "txt": "text/plain; charset=utf-8",
    }.get(suffix, "application/octet-stream")

    return StreamingResponse(iter([content]), media_type=media_type)
