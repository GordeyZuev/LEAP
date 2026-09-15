"""Shared validation and presign for small owner-uploaded images (covers, banners)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from config.settings import get_settings
from file_storage.factory import get_storage_backend

SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024


async def read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_IMAGE_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_FORMATS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {file_ext}. Supported: {supported}",
        )
    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {len(content) / 1024 / 1024:.1f}MB > 2MB",
        )
    return content, file_ext


async def presign_storage_keys(keys: list[str | None]) -> dict[str, str]:
    """Presign unique non-empty keys in one backend call. Missing keys are omitted."""
    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(key)
    if not unique:
        return {}
    storage = get_storage_backend()
    expires_in = get_settings().storage.s3_presign_expires
    urls = await storage.presigned_urls(unique, expires_in=expires_in)
    return {key: url for key, url in zip(unique, urls, strict=True) if url}


async def save_bytes(storage_key: str, content: bytes) -> str:
    return await get_storage_backend().save(storage_key, content)


async def delete_key_silent(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        await get_storage_backend().delete(storage_key)
    except Exception:
        return
