"""MTS Link downloader: streams the converted MP4 and fetches companion files.

Conversion ordering and waiting happen in ``api.services.mts_link_prepare`` before
the pipeline reaches download. This module only streams when UserAPI reports a
ready ``downloadUrl``.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from api.mts_link_api import (
    DEFAULT_BASE_URL,
    MtsLinkAPI,
    MtsLinkAPIError,
)
from file_storage.path_builder import StoragePathBuilder, to_storage_key
from logger import format_details, get_logger
from video_download_module.core.base import BaseDownloader, DownloadResult

logger = get_logger()

_ATTACHMENT_TIMEOUT = httpx.Timeout(timeout=120.0, connect=30.0)

_CONVERSION_DONE_STATES = {"complete", "completed", "done", "success", "finished"}

# Records and their MP4 renders also show up in the session file list; they are the
# recording itself, not an attachment.
_SKIP_FILE_TYPES = {"record", "convertedrecord", "converted_record"}

# Keeps Unicode letters: lecture slides are usually named in Russian, and an
# ASCII-only filter would reduce them to punctuation.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.-]+")
_MAX_FILENAME_LENGTH = 120


class MtsLinkConversionPendingError(MtsLinkAPIError):
    """Conversion is still running; the caller should retry later."""


def _safe_filename(name: str, fallback: str) -> str:
    """Flatten an attachment name into something safe for a storage key.

    Path separators cannot survive the character filter, so the result stays
    inside the recording folder. The manifest keeps the original name.
    """
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", (name or "").strip())
    cleaned = cleaned.replace("_.", ".").strip("._")
    if not cleaned:
        return fallback
    if len(cleaned) > _MAX_FILENAME_LENGTH:
        trimmed = Path(cleaned)
        keep = _MAX_FILENAME_LENGTH - len(trimmed.suffix)
        cleaned = trimmed.stem[:keep] + trimmed.suffix if keep > 0 else cleaned[:_MAX_FILENAME_LENGTH]
    return cleaned


class MtsLinkDownloader(BaseDownloader):
    """Downloads the converted MP4 of an MTS Link recording, plus chat and attachments."""

    def __init__(
        self,
        user_slug: int,
        storage_builder: StoragePathBuilder | None = None,
        *,
        api_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        conversion_quality: str = "720",
        conversion_view: str = "none",
        fetch_chat: bool = True,
        fetch_session_files: bool = True,
        **kwargs,  # noqa: ARG002
    ):
        super().__init__(user_slug, storage_builder)
        if not api_token:
            raise ValueError("MTS Link download requires an organization api_token")
        self.api = MtsLinkAPI(api_token=api_token, base_url=base_url)
        self.conversion_quality = conversion_quality
        self.conversion_view = conversion_view
        self.fetch_chat = fetch_chat
        self.fetch_session_files = fetch_session_files

    async def download(
        self,
        recording_id: int,
        source_meta: dict[str, Any],
        force: bool = False,
    ) -> DownloadResult:
        """Ensure an MP4 exists on MTS Link, stream it to storage, then fetch companions."""
        from file_storage.factory import get_storage_backend

        event_session_id = source_meta.get("event_session_id")
        record_id = source_meta.get("mts_record_id")
        if not event_session_id or not record_id:
            raise ValueError("MTS Link source metadata requires event_session_id and mts_record_id")

        target_key = self._get_target_key(recording_id, source_suffix=".mp4")
        storage_backend = get_storage_backend()

        if not force and await storage_backend.exists(target_key):
            existing_size = await storage_backend.get_size(target_key)
            if existing_size > 1024:
                return DownloadResult(storage_key=target_key, file_size=existing_size)

        download_url, conversion_id = await self._ensure_mp4(record_id, event_session_id, source_meta)

        temp_path = self._new_temp_path(".mp4")
        try:
            success = await self._download_url(
                url=download_url,
                filepath=temp_path,
                description="MTS Link MP4",
                source_name=f"mtslink{recording_id}.mp4",
            )
            if not success:
                raise RuntimeError(f"Failed to download MTS Link MP4 for recording {recording_id}")

            size = await self._commit_temp_to_storage(temp_path, target_key)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

        extras = await self._fetch_companions(recording_id, event_session_id)

        return DownloadResult(
            storage_key=target_key,
            file_size=size,
            metadata={
                "conversion_id": conversion_id,
                "conversion_state": "completed",
                "conversion_quality": self.conversion_quality,
                "conversion_view": self.conversion_view,
                "download_url": download_url,
                "needs_mp4": False,
                "extras": extras,
            },
        )

    async def _ensure_mp4(
        self,
        _record_id: int | str,
        event_session_id: int | str,
        source_meta: dict[str, Any],
    ) -> tuple[str, Any]:
        """Return a fresh MP4 URL when conversion already finished (prepare owns ordering/wait)."""
        ready_url = await self.api.get_ready_mp4_url(event_session_id)
        if ready_url:
            return ready_url, source_meta.get("conversion_id")

        raise MtsLinkConversionPendingError(
            f"MTS Link MP4 not ready for session {event_session_id}; use /run to prepare",
        )

    async def _fetch_companions(self, recording_id: int, event_session_id: int | str) -> dict[str, Any]:
        """Fetch chat and attachments next to the video, never failing the download."""
        extras: dict[str, Any] = {"chat": False, "files_count": 0, "error": None}
        errors: list[str] = []

        if self.fetch_chat:
            try:
                extras["chat"] = await self._save_chat(recording_id, event_session_id)
            except Exception as e:
                errors.append(f"chat: {e}")
                logger.warning(f"MTS Link chat not saved | {format_details(recording=recording_id, error=str(e))}")

        if self.fetch_session_files:
            try:
                extras["files_count"] = await self._save_session_files(recording_id, event_session_id)
            except Exception as e:
                errors.append(f"files: {e}")
                logger.warning(f"MTS Link files not saved | {format_details(recording=recording_id, error=str(e))}")

        if errors:
            extras["error"] = "; ".join(errors)
        return extras

    async def _save_chat(self, recording_id: int, event_session_id: int | str) -> bool:
        """Store the chat log as ``source_extras/chat.json``. Returns False when empty."""
        from file_storage.factory import get_storage_backend

        key = to_storage_key(self.storage.recording_source_chat(self.user_slug, recording_id))
        payload = await self.api.get_event_session_chat(event_session_id)
        if not payload:
            return False

        document = {
            "event_session_id": event_session_id,
            "fetched_at": datetime.now(UTC).isoformat(),
            "data": payload,
        }
        await get_storage_backend().save(key, json.dumps(document, ensure_ascii=False, indent=2).encode())
        logger.info(f"MTS Link chat saved | {format_details(recording=recording_id)}")
        return True

    async def _save_session_files(self, recording_id: int, event_session_id: int | str) -> int:
        """Store downloadable session attachments plus a manifest. Returns file count."""
        from file_storage.factory import get_storage_backend

        files = await self.api.list_event_session_files(event_session_id)
        storage_backend = get_storage_backend()
        manifest: list[dict[str, Any]] = []
        used_names: set[str] = set()

        for item in files:
            file_type = str(item.get("typeFile") or item.get("type") or "").lower()
            url = item.get("downloadUrl") or item.get("url")
            if file_type in _SKIP_FILE_TYPES or not url:
                continue

            file_id = item.get("id")
            name = _safe_filename(str(item.get("name") or ""), fallback=f"file_{file_id}")
            if name in used_names:
                name = f"{file_id}_{name}"
            used_names.add(name)

            key = to_storage_key(self.storage.recording_source_file(self.user_slug, recording_id, name))
            saved = await self._save_remote_file(str(url), key, storage_backend)
            if not saved:
                continue

            manifest.append(
                {
                    "mts_file_id": file_id,
                    "name": item.get("name"),
                    "stored_as": name,
                    "type": item.get("typeFile") or item.get("type"),
                    "size": saved,
                    "storage_key": key,
                }
            )

        if manifest:
            manifest_key = to_storage_key(self.storage.recording_source_files_manifest(self.user_slug, recording_id))
            await storage_backend.save(manifest_key, json.dumps(manifest, ensure_ascii=False, indent=2).encode())
            logger.info(f"MTS Link files saved | {format_details(recording=recording_id, files=len(manifest))}")

        return len(manifest)

    async def _save_remote_file(self, url: str, key: str, storage_backend) -> int | None:
        """Stream one attachment into storage. Returns its size, or None on failure.

        Deliberately not ``_download_url``: that path validates media containers and
        would reject slides, PDFs and other legitimate attachments.
        """
        temp_path: Path = self.storage.create_temp_file(prefix="mtsx_", suffix=Path(key).suffix)
        try:
            async with httpx.AsyncClient(timeout=_ATTACHMENT_TIMEOUT, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with temp_path.open("wb") as handle:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            handle.write(chunk)

            size = temp_path.stat().st_size
            if not size:
                return None

            await storage_backend.save_file(key, temp_path)
            return size
        except httpx.HTTPError as e:
            logger.warning(f"MTS Link attachment skipped | {format_details(file=Path(key).name, error=str(e))}")
            return None
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
