import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from file_storage.path_builder import StoragePathBuilder
from logger import get_logger
from models import MeetingRecording, ProcessingStatus

logger = get_logger()


class ZoomDownloader:
    """Downloads Zoom recordings with resume support and ID-based storage paths."""

    def __init__(self, user_slug: int, storage_builder: StoragePathBuilder | None = None):
        self.user_slug = user_slug
        self.storage = storage_builder or StoragePathBuilder()

    def _encode_download_url(self, url: str) -> str:
        """Double-encode URLs with special chars per Zoom API requirements."""
        if "==" in url or "//" in url:
            encoded = quote(url, safe="/:")
            return quote(encoded, safe="/:")
        return url


    async def download_file(
        self,
        url: str,
        filepath: Path,
        description: str = "file",
        expected_size: int | None = None,
        password: str | None = None,
        passcode: str | None = None,
        download_access_token: str | None = None,
        oauth_token: str | None = None,
        max_retries: int = 10,
    ) -> bool:
        """Download with resume support and exponential backoff retry."""

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry {attempt + 1}/{max_retries}: {description}")

                downloaded = 0
                if filepath.exists():
                    downloaded = filepath.stat().st_size
                    logger.info(f"Resuming from {downloaded / (1024 * 1024):.1f} MB")

                encoded_url = self._encode_download_url(url)
                headers = {}
                params = {}

                if oauth_token:
                    headers["Authorization"] = f"Bearer {oauth_token}"
                elif download_access_token:
                    headers["Authorization"] = f"Bearer {download_access_token}"
                elif passcode:
                    headers["X-Zoom-Passcode"] = passcode
                    headers["Authorization"] = f"Bearer {passcode}"
                elif password:
                    params["password"] = password
                    params["access_token"] = password
                else:
                    logger.warning("No authentication provided")

                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"

                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout=180.0, connect=30.0, read=60.0, write=30.0),
                    follow_redirects=True,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                ) as client:
                    async with client.stream("GET", encoded_url, headers=headers, params=params) as response:
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

                if not self._validate_downloaded_file(filepath, expected_size, total_size):
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
                status = e.response.status_code
                if status == 416 and filepath.exists():
                    filepath.unlink()
                    downloaded = 0
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue

                logger.error(f"HTTP {status} error: {description}")
                if filepath.exists() and status >= 400:
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

    def _validate_downloaded_file(
        self, filepath: Path, expected_size: int | None = None, total_size: int | None = None
    ) -> bool:
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

    async def download_recording(
        self,
        recording: MeetingRecording,
        force_download: bool = False,
    ) -> bool:
        """Downloads recording to storage/users/user_XXXXXX/recordings/{id}/source.mp4"""

        if not recording.video_file_download_url:
            logger.error(f"No video URL for recording {recording.db_id}")
            recording.mark_failure(
                reason="No video link",
                rollback_to_status=ProcessingStatus.INITIALIZED,
                failed_at_stage="downloading",
            )
            return False

        final_path = self.storage.recording_source(self.user_slug, recording.db_id)

        if (
            not force_download
            and recording.status == ProcessingStatus.DOWNLOADED
            and recording.local_video_path
            and Path(recording.local_video_path).exists()
        ):
            logger.info(f"Recording {recording.db_id} already downloaded, skipping")
            return False

        recording.update_status(ProcessingStatus.DOWNLOADING)

        logger.info(f"Downloading recording {recording.db_id}: {recording.display_name}")

        success = await self.download_file(
            recording.video_file_download_url,
            final_path,
            "video file",
            recording.video_file_size or 0,
            recording.password,
            recording.recording_play_passcode,
            recording.download_access_token,
            None,
            max_retries=10,
        )

        if not success:
            recording.mark_failure(
                reason="Error downloading file",
                rollback_to_status=ProcessingStatus.INITIALIZED,
                failed_at_stage="downloading",
            )
            logger.error(f"Download failed for recording {recording.db_id}")
            return False

        try:
            recording.local_video_path = str(final_path.relative_to(Path.cwd()))
        except ValueError:
            recording.local_video_path = str(final_path)
        recording.update_status(ProcessingStatus.DOWNLOADED)
        recording.downloaded_at = datetime.now()
        logger.info(f"Recording {recording.db_id} downloaded successfully")
        return True
