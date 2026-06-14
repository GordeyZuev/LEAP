"""Zoom video downloader with resume support."""

from datetime import UTC, datetime
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
        """Download a Zoom recording by source metadata to storage."""
        from config.settings import get_settings
        from file_storage.factory import get_storage_backend
        from utils.pipeline_video_formats import (
            pipeline_ingress_suffixes_from_settings_formats,
            strict_suffix_from_source_name,
        )

        download_url = source_meta.get("download_url")
        if not download_url:
            raise ValueError("No download_url in source metadata")

        allowed = pipeline_ingress_suffixes_from_settings_formats(
            get_settings().storage.supported_video_formats,
        )
        source_suffix = strict_suffix_from_source_name(source_meta.get("name"), allowed)
        target_key = self._get_target_key(recording_id, source_suffix=source_suffix)
        validate_name = source_meta.get("name") or f"zoom{source_suffix}"

        storage_backend = get_storage_backend()

        # Skip if already in storage and not forced
        if not force and await storage_backend.exists(target_key):
            existing_size = await storage_backend.get_size(target_key)
            if existing_size > 1024:
                return DownloadResult(storage_key=target_key, file_size=existing_size)

        encoded_url = self._encode_download_url(download_url)
        headers, params = self._build_zoom_auth(
            password=source_meta.get("password"),
            passcode=source_meta.get("recording_play_passcode"),
            download_access_token=source_meta.get("download_access_token"),
        )

        temp_path = self._new_temp_path(source_suffix)
        try:
            success = await self._download_url(
                url=encoded_url,
                filepath=temp_path,
                headers=headers,
                params=params,
                expected_size=source_meta.get("file_size", 0) or None,
                description="Zoom recording",
                source_name=validate_name,
            )

            if not success:
                raise RuntimeError(f"Failed to download Zoom recording {recording_id}")

            size = await self._commit_temp_to_storage(temp_path, target_key)
            return DownloadResult(storage_key=target_key, file_size=size)
        finally:
            # Safety: if commit threw, the temp may still be around.
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    async def download_recording(
        self,
        recording: MeetingRecording,
        force_download: bool = False,
        *,
        source_suffix: str = ".mp4",
    ) -> bool:
        """Download Zoom recording to ``source.<suffix>`` (default ``source.mp4``)."""
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

        from file_storage.factory import get_storage_backend

        target_key = self._get_target_key(recording.db_id, source_suffix=source_suffix)
        validate_as_name = f"zoom-recording{source_suffix}"
        storage_backend = get_storage_backend()

        if (
            not force_download
            and recording.status == ProcessingStatus.DOWNLOADED
            and recording.local_video_path
            and await storage_backend.exists(recording.local_video_path)
        ):
            logger.info(f"Skipped: already downloaded | rec={recording.db_id}")
            return False

        recording.update_status(ProcessingStatus.DOWNLOADING)
        recording.download_started_at = datetime.now(UTC)
        logger.info(f"Downloading | rec={recording.db_id}")
        logger.debug(f"Recording name: {recording.display_name}")

        encoded_url = self._encode_download_url(recording.video_file_download_url)
        headers, params = self._build_zoom_auth(
            password=recording.password,
            passcode=recording.recording_play_passcode,
            download_access_token=recording.download_access_token,
        )

        temp_path = self._new_temp_path(source_suffix)
        try:
            success = await self._download_url(
                url=encoded_url,
                filepath=temp_path,
                headers=headers,
                params=params,
                expected_size=recording.video_file_size or None,
                description="video file",
                source_name=validate_as_name,
            )

            if not success:
                recording.mark_failure(
                    reason="Error downloading file",
                    rollback_to_status=ProcessingStatus.INITIALIZED,
                    failed_at_stage="downloading",
                )
                logger.error(f"Download failed for recording {recording.db_id}")
                return False

            await self._commit_temp_to_storage(temp_path, target_key)
            recording.local_video_path = target_key
            recording.update_status(ProcessingStatus.DOWNLOADED)
            recording.downloaded_at = datetime.now(UTC)
            logger.info(f"Downloaded | rec={recording.db_id}")
            return True
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
