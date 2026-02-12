"""Zoom video downloader with resume support."""

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from logger import get_logger
from models import MeetingRecording, ProcessingStatus

from .core.base import BaseDownloader, DownloadResult

logger = get_logger()


class ZoomDownloader(BaseDownloader):
    """Downloads Zoom recordings with resume support and ID-based storage paths."""

    def _encode_download_url(self, url: str) -> str:
        """Double-encode URLs with special chars per Zoom API requirements."""
        if "==" in url or "//" in url:
            encoded = quote(url, safe="/:")
            return quote(encoded, safe="/:")
        return url

    def _build_zoom_auth(
        self,
        password: str | None = None,
        passcode: str | None = None,
        download_access_token: str | None = None,
        oauth_token: str | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Build Zoom-specific auth headers and params."""
        headers: dict[str, str] = {}
        params: dict[str, str] = {}

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

        return headers, params

    async def download(
        self,
        recording_id: int,
        source_meta: dict[str, Any],
        force: bool = False,
    ) -> DownloadResult:
        """Download a Zoom recording by source metadata."""
        download_url = source_meta.get("download_url")
        if not download_url:
            raise ValueError("No download_url in source metadata")

        target_path = self._get_target_path(recording_id)

        if not force and target_path.exists() and target_path.stat().st_size > 1024:
            return DownloadResult(
                file_path=target_path,
                file_size=target_path.stat().st_size,
            )

        encoded_url = self._encode_download_url(download_url)
        headers, params = self._build_zoom_auth(
            password=source_meta.get("password"),
            passcode=source_meta.get("recording_play_passcode"),
            download_access_token=source_meta.get("download_access_token"),
        )

        success = await self._download_url(
            url=encoded_url,
            filepath=target_path,
            headers=headers,
            params=params,
            expected_size=source_meta.get("file_size", 0) or None,
            description="Zoom recording",
        )

        if not success:
            raise RuntimeError(f"Failed to download Zoom recording {recording_id}")

        return DownloadResult(
            file_path=target_path,
            file_size=target_path.stat().st_size,
        )

    async def download_recording(
        self,
        recording: MeetingRecording,
        force_download: bool = False,
    ) -> bool:
        """Downloads Zoom recording to storage/users/user_XXXXXX/recordings/{id}/source.mp4"""
        if not recording.video_file_download_url:
            logger.error(f"No video URL for recording {recording.db_id}")
            recording.mark_failure(
                reason="No video link",
                rollback_to_status=ProcessingStatus.INITIALIZED,
                failed_at_stage="downloading",
            )
            return False

        if recording.db_id is None:
            logger.error("Recording has no db_id, cannot determine storage path")
            recording.mark_failure(
                reason="No database ID",
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

        encoded_url = self._encode_download_url(recording.video_file_download_url)
        headers, params = self._build_zoom_auth(
            password=recording.password,
            passcode=recording.recording_play_passcode,
            download_access_token=recording.download_access_token,
        )

        success = await self._download_url(
            url=encoded_url,
            filepath=final_path,
            headers=headers,
            params=params,
            expected_size=recording.video_file_size or None,
            description="video file",
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
