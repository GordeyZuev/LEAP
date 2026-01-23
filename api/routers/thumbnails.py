"""User thumbnail endpoints"""

import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from api.auth.dependencies import get_current_user
from api.schemas.thumbnail import (
    ThumbnailInfo,
    ThumbnailListResponse,
    ThumbnailUploadResponse,
)
from database.auth_models import UserModel
from logger import get_logger
from utils.thumbnail_manager import get_thumbnail_manager

logger = get_logger()
router = APIRouter(prefix="/api/v1/thumbnails", tags=["Thumbnails"])

# Constants
FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_FILENAME_LENGTH = 100
SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg"}  # Supported thumbnail formats


def validate_filename(filename: str, strict: bool = True) -> str:
    """
    Validate and normalize filename.

    Args:
        filename: Filename to validate (without extension)
        strict: If True, reject invalid characters. If False, replace them with underscore.

    Returns:
        Validated/sanitized filename

    Raises:
        ValueError: If filename is invalid (empty, only extension, no valid chars)
    """
    filename = filename.strip()

    if not filename:
        raise ValueError("Filename cannot be empty")

    filename = Path(filename).stem

    if not filename:
        raise ValueError("Filename cannot be only an extension")

    if strict:
        if not FILENAME_PATTERN.match(filename):
            raise ValueError(
                "Filename can only contain English letters, numbers, dash (-), and underscore (_)"
            )
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
    """
    Validate thumbnail name to prevent path traversal attacks.

    Args:
        thumbnail_name: Thumbnail file name to validate

    Raises:
        HTTPException: If thumbnail name contains path separators or starts with dot
    """
    if "/" in thumbnail_name or "\\" in thumbnail_name or thumbnail_name.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thumbnail name",
        )


def _build_thumbnail_info(thumbnail_path: Path, is_template: bool) -> ThumbnailInfo:
    """
    Build ThumbnailInfo from path.

    Returns URL endpoint instead of filesystem path for security.
    """
    thumbnail_manager = get_thumbnail_manager()
    # Build REST API URL instead of exposing filesystem path
    url = f"/api/v1/thumbnails/{thumbnail_path.name}"

    return ThumbnailInfo(
        name=thumbnail_path.name,
        url=url,
        is_template=is_template,
        **thumbnail_manager.get_thumbnail_info(thumbnail_path),
    )


async def _validate_and_read_file(file: UploadFile) -> tuple[bytes, str]:
    """
    Validate uploaded file and read its content.

    Args:
        file: Uploaded file

    Returns:
        Tuple of (file_content, file_extension)

    Raises:
        HTTPException: If validation fails
    """
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
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> ThumbnailListResponse:
    """
    Get list of user thumbnails.

    Returns all thumbnails in user's directory, including copies of shared
    templates that were copied during registration.

    Users can upload, modify, or delete any thumbnails in their directory.
    """
    thumbnail_manager = get_thumbnail_manager()

    thumbnails = thumbnail_manager.list_user_thumbnails(current_user.user_slug)
    items = [_build_thumbnail_info(thumb, is_template=False) for thumb in thumbnails]

    return ThumbnailListResponse(thumbnails=items)


@router.post("", response_model=ThumbnailUploadResponse, status_code=status.HTTP_201_CREATED)
async def create_thumbnail(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    file: UploadFile = File(...),
    custom_filename: str | None = Form(None),
) -> ThumbnailUploadResponse:
    """
    Create new thumbnail (fails if already exists).

    Use PUT to update existing thumbnail.

    Supported formats: PNG, JPG, JPEG
    Max size: 2MB (YouTube recommendation)

    Args:
        file: Uploaded file
        custom_filename: Custom filename (without extension). Only alphanumeric characters, dash, and underscore allowed.
                        Min length: 1, max length: 100.
                        Example: file="abc123.png" + custom_filename="photo" -> saved as "photo.png"

    Returns:
        201 Created: Thumbnail created successfully
        409 Conflict: Thumbnail already exists (use PUT to update)
    """
    content, file_ext = await _validate_and_read_file(file)

    try:
        if custom_filename:
            validated_name = validate_filename(custom_filename, strict=True)
        else:
            validated_name = validate_filename(file.filename, strict=False)

        final_filename = f"{validated_name}{file_ext}"

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    thumbnail_manager = get_thumbnail_manager()
    user_thumbs_dir = thumbnail_manager.get_user_thumbnails_dir(current_user.user_slug)
    target_path = user_thumbs_dir / final_filename

    try:
        user_thumbs_dir.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Thumbnail '{final_filename}' already exists. Use PUT to update it.",
            )

        with target_path.open("wb") as f:
            f.write(content)

        logger.info(f"User {current_user.user_slug} created thumbnail: {final_filename}")

        return ThumbnailUploadResponse(
            message="Thumbnail created successfully",
            thumbnail=_build_thumbnail_info(target_path, is_template=False),
        )

    except OSError as e:
        logger.error(f"File system error for user {current_user.user_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save thumbnail due to file system error",
        )
    except Exception as e:
        logger.error(f"Unexpected error creating thumbnail for user {current_user.user_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create thumbnail: {e!s}",
        )


@router.put("/{thumbnail_name}", response_model=ThumbnailUploadResponse)
async def update_thumbnail(
    thumbnail_name: str,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ThumbnailUploadResponse:
    """
    Update existing thumbnail (or create if doesn't exist).

    This is an idempotent operation - calling it multiple times with the same data
    will have the same result.

    Supported formats: PNG, JPG, JPEG
    Max size: 2MB (YouTube recommendation)

    Args:
        thumbnail_name: Name of the thumbnail to update
        file: Uploaded file

    Returns:
        200 OK: Thumbnail updated successfully
        201 Created: Thumbnail created (if it didn't exist)
    """
    _validate_thumbnail_name(thumbnail_name)
    content, file_ext = await _validate_and_read_file(file)

    name_without_ext = Path(thumbnail_name).stem
    expected_filename = f"{name_without_ext}{file_ext}"

    if thumbnail_name != expected_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension mismatch. Expected '{thumbnail_name}', but uploaded file has '{file_ext}' extension.",
        )

    thumbnail_manager = get_thumbnail_manager()
    user_thumbs_dir = thumbnail_manager.get_user_thumbnails_dir(current_user.user_slug)
    target_path = user_thumbs_dir / thumbnail_name

    try:
        user_thumbs_dir.mkdir(parents=True, exist_ok=True)

        is_update = target_path.exists()
        action = "updated" if is_update else "created"

        with target_path.open("wb") as f:
            f.write(content)

        logger.info(f"User {current_user.user_slug} {action} thumbnail: {thumbnail_name}")

        return ThumbnailUploadResponse(
            message=f"Thumbnail {action} successfully",
            thumbnail=_build_thumbnail_info(target_path, is_template=False),
        )

    except OSError as e:
        logger.error(f"File system error for user {current_user.user_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save thumbnail due to file system error",
        )
    except Exception as e:
        logger.error(f"Unexpected error updating thumbnail for user {current_user.user_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update thumbnail: {e!s}",
        )


@router.get("/{thumbnail_name}")
async def get_thumbnail_file(
    thumbnail_name: str,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    use_template: bool = True,
) -> FileResponse:
    """
    Get thumbnail file (for viewing or downloading).

    Args:
        thumbnail_name: Thumbnail file name
        use_template: Search in templates if not found in user's thumbnails
    """
    _validate_thumbnail_name(thumbnail_name)
    thumbnail_manager = get_thumbnail_manager()

    thumbnail_path = thumbnail_manager.get_thumbnail_path(
        user_slug=current_user.user_slug,
        thumbnail_name=thumbnail_name,
        fallback_to_template=use_template,
    )

    if not thumbnail_path or not thumbnail_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thumbnail not found: {thumbnail_name}",
        )

    file_ext = thumbnail_path.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    media_type = media_type_map.get(file_ext, "image/png")

    return FileResponse(
        path=thumbnail_path,
        media_type=media_type,
        filename=thumbnail_path.name,
    )


@router.delete("/{thumbnail_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thumbnail(
    thumbnail_name: str,
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> None:
    """
    Delete user thumbnail.

    Cannot delete global templates.
    """
    _validate_thumbnail_name(thumbnail_name)
    thumbnail_manager = get_thumbnail_manager()

    success = thumbnail_manager.delete_user_thumbnail(
        user_slug=current_user.user_slug,
        thumbnail_name=thumbnail_name,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thumbnail not found: {thumbnail_name}",
        )

    logger.info(f"User {current_user.user_slug} deleted thumbnail: {thumbnail_name}")
