"""Base downloader classes and data structures.

Downloaders stream remote video into a **local temp file** and then commit it
to the storage backend (S3 or LOCAL) via ``save_file``. Resume of partial
downloads happens against the temp file — once committed, the file lives only
in storage.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from file_storage.factory import get_storage_backend
from file_storage.path_builder import StoragePathBuilder, to_storage_key
from logger import get_logger

logger = get_logger()


@dataclass
class DownloadResult:
    """Video download result.

    ``storage_key`` is the canonical storage key (e.g.
    ``users/000001/recordings/42/source.mp4``); use this for DB writes.
    ``file_path`` is kept for backward compat with callers that haven't been
    updated yet — for the local backend it points at the actual file on disk,
    for S3 it equals the storage key.
    """

    storage_key: str
    file_size: int
    duration: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def file_path(self) -> Path:
        """Backward-compat accessor; callers should migrate to ``storage_key``."""
        return Path(self.storage_key)


class BaseDownloader(ABC):
    """Base downloader class for all video sources."""

    def __init__(self, user_slug: int, storage_builder: StoragePathBuilder | None = None):
        self.user_slug = user_slug
        self.storage = storage_builder or StoragePathBuilder()

    @abstractmethod
    async def download(
        self,
        recording_id: int,
        source_meta: dict[str, Any],
        force: bool = False,
    ) -> DownloadResult:
        """Download video file. Returns DownloadResult with storage_key and metadata."""

    def _get_target_path(self, recording_id: int, source_suffix: str = ".mp4") -> Path:
        """Path-builder Path under recording folder (default aligns with Zoom MP4 naming).

        This is a path/key generator only — no file is written here. Subclasses
        use :meth:`_get_target_key` for the storage key form, or pass the Path
        through :func:`to_storage_key` themselves.
        """
        suf = source_suffix if source_suffix.startswith(".") else f".{source_suffix}"
        return self.storage.recording_source(self.user_slug, recording_id, suffix=suf)

    def _get_target_key(self, recording_id: int, source_suffix: str = ".mp4") -> str:
        """Storage key for the recording's source video (canonical form)."""
        return to_storage_key(self._get_target_path(recording_id, source_suffix))

    def _new_temp_path(self, source_suffix: str = ".mp4") -> Path:
        """Allocate a unique local temp file for streaming downloads."""
        suf = source_suffix if source_suffix.startswith(".") else f".{source_suffix}"
        return self.storage.create_temp_file(prefix="dl_", suffix=suf)

    async def _commit_temp_to_storage(self, temp_path: Path, target_key: str) -> int:
        """Move the temp file into storage and return final size in bytes.

        Returns size from the temp file before commit (cheap stat). After this
        call the temp file is consumed (moved on LOCAL backend, uploaded+deleted
        in the caller's finally on S3).
        """
        size = temp_path.stat().st_size
        storage = get_storage_backend()
        await storage.save_file(target_key, temp_path)
        # ``save_file`` consumes the temp file on the LOCAL backend (shutil.move);
        # on S3 the file is uploaded but the local copy remains. Ensure cleanup.
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        return size

    async def _download_url(
        self,
        url: str,
        filepath: Path,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        expected_size: int | None = None,
        max_retries: int = 10,
        description: str = "file",
        source_name: str | None = None,
    ) -> bool:
        """Stream a remote URL into ``filepath`` with resume support.

        ``filepath`` should be a **local temp file**; caller is responsible for
        committing successfully-downloaded contents to storage via
        :meth:`_commit_temp_to_storage` and for deleting the temp on failure.
        """
        headers = dict(headers) if headers else {}
        params = dict(params) if params else {}
        cookies = dict(cookies) if cookies else {}

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry {attempt + 1}/{max_retries}: {description}")

                downloaded = 0
                if filepath.exists():
                    downloaded = filepath.stat().st_size
                    logger.info(f"Resuming from {downloaded / (1024 * 1024):.1f} MB")

                req_headers = dict(headers)
                if downloaded > 0:
                    req_headers["Range"] = f"bytes={downloaded}-"

                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout=180.0, connect=30.0, read=60.0, write=30.0),
                    follow_redirects=True,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                ) as client:
                    async with client.stream(
                        "GET", url, headers=req_headers, params=params, cookies=cookies or None
                    ) as response:
                        if downloaded > 0 and response.status_code == 206:
                            mode = "ab"
                        elif downloaded > 0 and response.status_code == 200:
                            logger.warning("Server doesn't support resume, restarting")
                            downloaded = 0
                            mode = "wb"
                            if filepath.exists():
                                filepath.unlink()
                        else:
                            response.raise_for_status()
                            mode = "wb"

                        filepath.parent.mkdir(parents=True, exist_ok=True)

                        content_range = response.headers.get("content-range")
                        if content_range:
                            total_size = int(content_range.split("/")[-1])
                        else:
                            total_size = int(response.headers.get("content-length", 0))
                            if downloaded > 0 and mode == "ab":
                                total_size += downloaded

                        if total_size == 0 and expected_size:
                            total_size = expected_size

                        with filepath.open(mode) as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)
                                downloaded += len(chunk)

                        logger.info(f"Downloaded {downloaded / (1024 * 1024):.1f} MB")

                if not self._validate_file(filepath, expected_size, total_size, source_name=source_name):
                    if attempt < max_retries - 1:
                        wait_time = 3 if attempt < 2 else 5
                        await asyncio.sleep(wait_time)
                        continue
                    logger.error(f"Download validation failed: {description}")
                    if filepath.exists():
                        filepath.unlink()
                    return False

                return True

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
                logger.warning(f"Network error: {type(e).__name__}")
                if attempt < max_retries - 1:
                    wait_time = 3 + attempt * 2 if attempt < 2 else min(10 + (attempt - 2) * 5, 30)
                    await asyncio.sleep(wait_time)
                    continue
                return False

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code == 416 and filepath.exists():
                    filepath.unlink()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue

                logger.error(f"HTTP {status_code} error: {description}")
                if filepath.exists() and status_code >= 400:
                    filepath.unlink()
                return False

            except Exception as e:
                logger.error(f"Unexpected error: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                if filepath.exists():
                    filepath.unlink()
                return False

        return False

    def _validate_file(
        self,
        filepath: Path,
        expected_size: int | None = None,
        total_size: int | None = None,
        source_name: str | None = None,
    ) -> bool:
        """Validate downloaded file size + container sniff (catches WebM saved as ``*.mp4``)."""
        try:
            from config.settings import get_settings
            from utils.pipeline_video_formats import ingress_validate_saved_media

            return ingress_validate_saved_media(
                filepath,
                expected_size,
                total_size,
                source_name,
                ingress_format_strings=get_settings().storage.supported_video_formats,
            )

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
