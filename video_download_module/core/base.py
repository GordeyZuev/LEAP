"""Base downloader classes and data structures."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from file_storage.path_builder import StoragePathBuilder
from logger import get_logger

logger = get_logger()


@dataclass
class DownloadResult:
    """Video download result."""

    file_path: Path
    file_size: int
    duration: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
        """Download video file. Returns DownloadResult with file path and metadata."""

    def _get_target_path(self, recording_id: int) -> Path:
        """Standard target path: storage/users/user_XXXXXX/recordings/{id}/source.mp4"""
        return self.storage.recording_source(self.user_slug, recording_id)

    async def _download_url(
        self,
        url: str,
        filepath: Path,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        expected_size: int | None = None,
        max_retries: int = 10,
        description: str = "file",
    ) -> bool:
        """Generic httpx streaming download with resume support and retries."""
        headers = dict(headers) if headers else {}
        params = dict(params) if params else {}

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
                    async with client.stream("GET", url, headers=req_headers, params=params) as response:
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

                if not self._validate_file(filepath, expected_size, total_size):
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

    def _validate_file(self, filepath: Path, expected_size: int | None = None, total_size: int | None = None) -> bool:
        """Validates file integrity by size and content type."""
        try:
            if not filepath.exists():
                return False

            file_size = filepath.stat().st_size
            if file_size < 1024:
                return False

            reference_size = total_size or expected_size
            if reference_size:
                if file_size < reference_size:
                    logger.warning(f"Incomplete: {(file_size / reference_size * 100):.1f}%")
                    return False
                if file_size > reference_size * 1.1:
                    logger.warning("File size exceeds expected by >10%")

            with filepath.open("rb") as f:
                first_chunk = f.read(1024)
                if b"<html" in first_chunk.lower() or b"<!doctype html" in first_chunk.lower():
                    logger.error("Downloaded HTML instead of media file")
                    return False

                if filepath.suffix.lower() == ".mp4":
                    if not (
                        first_chunk.startswith(b"\x00\x00\x00") or b"ftyp" in first_chunk or b"moov" in first_chunk
                    ):
                        logger.error("Invalid MP4 format")
                        return False

            return True

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
