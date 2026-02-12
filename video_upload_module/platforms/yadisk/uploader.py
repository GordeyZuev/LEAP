"""Yandex Disk uploader -- uploads processed video files to Yandex Disk."""

from datetime import datetime
from pathlib import Path
from typing import Any

from logger import get_logger
from video_upload_module.core.base import BaseUploader, UploadResult

logger = get_logger()


class YandexDiskUploader(BaseUploader):
    """Uploads video files to Yandex Disk via REST API."""

    def __init__(self, config, oauth_token: str | None = None):
        super().__init__(config)
        self.oauth_token = oauth_token

    async def authenticate(self) -> bool:
        """Verify OAuth token by checking disk info."""
        if not self.oauth_token:
            logger.error("No OAuth token for Yandex Disk")
            return False

        from yandex_disk_module.client import BASE_URL, YandexDiskClient, YandexDiskError

        client = YandexDiskClient(oauth_token=self.oauth_token)
        try:
            await client._request("GET", BASE_URL)
            self._authenticated = True
            return True
        except YandexDiskError as e:
            logger.error(f"Yandex Disk authentication failed: {e}")
            return False

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",  # noqa: ARG002
        progress=None,  # noqa: ARG002
        task_id=None,  # noqa: ARG002
        **kwargs,
    ) -> UploadResult | None:
        """Upload video to Yandex Disk.

        Kwargs:
            folder_path: Target folder on Disk (e.g. '/Video/Processed')
            filename: Custom filename (default: original filename)
            overwrite: Whether to overwrite existing file
        """
        from yandex_disk_module.client import YandexDiskClient, YandexDiskError

        local_path = Path(video_path)
        valid, msg = self.validate_file(video_path)
        if not valid:
            return UploadResult(
                video_id="",
                video_url="",
                title=title,
                upload_time=datetime.now(),
                status="failed",
                platform="yandex_disk",
                error_message=msg,
            )

        folder_path = kwargs.get("folder_path", "/Video/Uploads")
        filename = kwargs.get("filename") or local_path.name
        overwrite = kwargs.get("overwrite", False)
        disk_path = f"{folder_path}/{filename}"

        client = YandexDiskClient(oauth_token=self.oauth_token)

        try:
            success = await client.upload_file(
                local_path=local_path,
                disk_path=disk_path,
                overwrite=overwrite,
            )

            if success:
                public_url = f"disk:{disk_path}"

                return self._create_result(
                    video_id=disk_path,
                    video_url=public_url,
                    title=title,
                    platform="yandex_disk",
                    metadata={
                        "disk_path": disk_path,
                        "folder_path": folder_path,
                        "filename": filename,
                    },
                )

            return UploadResult(
                video_id="",
                video_url="",
                title=title,
                upload_time=datetime.now(),
                status="failed",
                platform="yandex_disk",
                error_message="Upload returned False",
            )

        except YandexDiskError as e:
            logger.error(f"Yandex Disk upload failed: {e}")
            return UploadResult(
                video_id="",
                video_url="",
                title=title,
                upload_time=datetime.now(),
                status="failed",
                platform="yandex_disk",
                error_message=str(e),
            )

    async def get_video_info(self, video_id: str) -> dict[str, Any] | None:
        """Get file info from Yandex Disk. video_id is the disk path."""
        from yandex_disk_module.client import BASE_URL, YandexDiskClient, YandexDiskError

        client = YandexDiskClient(oauth_token=self.oauth_token)
        try:
            return await client._request(
                "GET",
                f"{BASE_URL}/resources",
                params={"path": video_id},
            )
        except YandexDiskError:
            return None

    async def delete_video(self, video_id: str) -> bool:
        """Delete file from Yandex Disk. video_id is the disk path."""
        from yandex_disk_module.client import BASE_URL, YandexDiskClient, YandexDiskError

        client = YandexDiskClient(oauth_token=self.oauth_token)
        try:
            await client._request(
                "DELETE",
                f"{BASE_URL}/resources",
                params={"path": video_id, "permanently": "false"},
            )
            return True
        except YandexDiskError:
            return False
