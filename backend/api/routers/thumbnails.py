"""User thumbnail endpoints (storage-backend backed)."""

import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api.auth.dependencies import get_current_user
from api.schemas.auth import UserInDB
from api.schemas.thumbnail import (
    ThumbnailInfo,
    ThumbnailListResponse,
    ThumbnailUploadResponse,
)
from file_storage.factory import get_storage_backend
from logger import get_logger
from utils.thumbnail_manager import get_thumbnail_manager

logger = get_logger()
router = APIRouter(prefix="/api/v1/thumbnails", tags=["Thumbnails"])

# Constants
FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_FILENAME_LENGTH = 100
SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg"}  # Supported thumbnail formats


def validate_filename(filename: str, strict: bool = True) -> str:
    """Validate and normalize filename."""
    filename = filename.strip()

    if not filename:
        raise ValueError("Filename cannot be empty")

    filename = Path(filename).stem

    if not filename:
        raise ValueError("Filename cannot be only an extension")

    if strict:
        if not FILENAME_PATTERN.match(filename):
            raise ValueError("Filename can only contain English letters, numbers, dash (-), and underscore (_)")
    else:
        filename = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
        filename = filename.strip("_")

        if not filename:
            raise ValueError("Filename contains no valid characters")

    if len(filename) > MAX_FILENAME_LENGTH:
        if strict:
            raise ValueError(f"Filename too long (max {MAX_FILENAME_LENGTH} characters)")
        filename = filename[:MAX_FILENAME_LENGTH]

    return filename


def _validate_thumbnail_name(thumbnail_name: str) -> None:
    """Reject path-traversal attempts in user-supplied thumbnail names."""
    if "/" in thumbnail_name or "\\" in thumbnail_name or thumbnail_name.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thumbnail name",
        )


async def _build_thumbnail_info(storage_key: str, is_template: bool) -> ThumbnailInfo:
    """Build a ThumbnailInfo response from a storage key."""
    thumbnail_manager = get_thumbnail_manager()
    name = storage_key.rsplit("/", 1)[-1]
    url = f"/api/v1/thumbnails/{name}"
    return ThumbnailInfo(
        name=name,
        url=url,
        is_template=is_template,
        **(await thumbnail_manager.get_thumbnail_info(storage_key)),
    )


async def _validate_and_read_file(file: UploadFile) -> tuple[bytes, str]:
    """Validate uploaded file and read its bytes."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_IMAGE_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_FORMATS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {file_ext}. Supported: {supported}",
        )

    max_size = 2 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {len(content) / 1024 / 1024:.1f}MB > 2MB",
        )

    return content, file_ext


@router.get("", response_model=ThumbnailListResponse)
async def list_thumbnails(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> ThumbnailListResponse:
    """List user thumbnails (each entry references a storage key)."""
    thumbnail_manager = get_thumbnail_manager()
    keys = await thumbnail_manager.list_user_thumbnails(current_user.user_slug)
    items = [await _build_thumbnail_info(key, is_template=False) for key in keys]
    return ThumbnailListResponse(thumbnails=items)


@router.post("", response_model=ThumbnailUploadResponse, status_code=status.HTTP_201_CREATED)
async def create_thumbnail(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    file: UploadFile = File(...),
    custom_filename: str | None = Form(None),
) -> ThumbnailUploadResponse:
    """Create a new thumbnail (409 if it already exists)."""
    content, file_ext = await _validate_and_read_file(file)

    try:
        if custom_filename:
            validated_name = validate_filename(custom_filename, strict=True)
        else:
            validated_name = validate_filename(file.filename, strict=False)
        final_filename = f"{validated_name}{file_ext}"
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    thumbnail_manager = get_thumbnail_manager()
    if await thumbnail_manager.thumbnail_exists(current_user.user_slug, final_filename):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Thumbnail '{final_filename}' already exists. Use PUT to update it.",
        )

    try:
        storage_key = await thumbnail_manager.write_user_thumbnail(current_user.user_slug, final_filename, content)
        logger.info(f"User {current_user.user_slug} created thumbnail: {final_filename}")
        return ThumbnailUploadResponse(
            message="Thumbnail created successfully",
            thumbnail=await _build_thumbnail_info(storage_key, is_template=False),
        )
    except Exception as e:
        logger.error(f"Failed to create thumbnail for user {current_user.user_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create thumbnail: {e!s}",
        )


@router.put("/{thumbnail_name}", response_model=ThumbnailUploadResponse)
async def update_thumbnail(
    thumbnail_name: str,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ThumbnailUploadResponse:
    """Update an existing thumbnail (or create it). Idempotent."""
    _validate_thumbnail_name(thumbnail_name)
    content, file_ext = await _validate_and_read_file(file)

    name_without_ext = Path(thumbnail_name).stem
    expected_filename = f"{name_without_ext}{file_ext}"

    if thumbnail_name != expected_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File extension mismatch. Expected '{thumbnail_name}', but uploaded file has '{file_ext}' extension."
            ),
        )

    thumbnail_manager = get_thumbnail_manager()
    is_update = await thumbnail_manager.thumbnail_exists(current_user.user_slug, thumbnail_name)
    action = "updated" if is_update else "created"

    try:
        storage_key = await thumbnail_manager.write_user_thumbnail(current_user.user_slug, thumbnail_name, content)
        logger.info(f"User {current_user.user_slug} {action} thumbnail: {thumbnail_name}")
        return ThumbnailUploadResponse(
            message=f"Thumbnail {action} successfully",
            thumbnail=await _build_thumbnail_info(storage_key, is_template=False),
        )
    except Exception as e:
        logger.error(f"Failed to update thumbnail for user {current_user.user_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update thumbnail: {e!s}",
        )


@router.get("/{thumbnail_name}")
async def get_thumbnail_file(
    thumbnail_name: str,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    use_template: bool = True,
) -> StreamingResponse:
    """Stream a thumbnail's bytes (user-side first, shared template as fallback)."""
    _validate_thumbnail_name(thumbnail_name)
    thumbnail_manager = get_thumbnail_manager()

    key = await thumbnail_manager.get_thumbnail_key(
        user_slug=current_user.user_slug,
        thumbnail_name=thumbnail_name,
        fallback_to_template=use_template,
    )
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thumbnail not found: {thumbnail_name}",
        )

    file_ext = Path(thumbnail_name).suffix.lower()
    media_type_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    media_type = media_type_map.get(file_ext, "image/png")

    storage = get_storage_backend()
    content = await storage.load(key)
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{thumbnail_name}"'},
    )


@router.delete("/{thumbnail_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thumbnail(
    thumbnail_name: str,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> None:
    """Delete a user thumbnail (global templates are not deletable here)."""
    _validate_thumbnail_name(thumbnail_name)
    thumbnail_manager = get_thumbnail_manager()

    success = await thumbnail_manager.delete_user_thumbnail(
        user_slug=current_user.user_slug,
        thumbnail_name=thumbnail_name,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thumbnail not found: {thumbnail_name}",
        )

    logger.info(f"User {current_user.user_slug} deleted thumbnail: {thumbnail_name}")
