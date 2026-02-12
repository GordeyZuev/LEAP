"""Yandex Disk video downloader."""

from typing import Any

from file_storage.path_builder import StoragePathBuilder
from logger import get_logger
from video_download_module.core.base import BaseDownloader, DownloadResult

logger = get_logger()


class YandexDiskDownloader(BaseDownloader):
    """Downloads video files from Yandex Disk via REST API."""

    def __init__(
        self,
        user_slug: int,
        storage_builder: StoragePathBuilder | None = None,
        oauth_token: str | None = None,
        **kwargs,  # noqa: ARG002
    ):
        super().__init__(user_slug, storage_builder)
        self.oauth_token = oauth_token

    async def download(
        self,
        recording_id: int,
        source_meta: dict[str, Any],
        force: bool = False,
    ) -> DownloadResult:
        """Download video from Yandex Disk (API or public link)."""
        from yandex_disk_module.client import YandexDiskClient

        target_path = self._get_target_path(recording_id)

        if not force and target_path.exists() and target_path.stat().st_size > 1024:
            return DownloadResult(
                file_path=target_path,
                file_size=target_path.stat().st_size,
            )

        download_method = source_meta.get("download_method", "api")
        oauth_token = self.oauth_token or source_meta.get("oauth_token")

        client = YandexDiskClient(oauth_token=oauth_token)

        # Get temporary download URL from Yandex Disk API
        if download_method == "public":
            public_key = source_meta.get("public_key", "")
            file_path = source_meta.get("path")
            download_url = await client.get_public_download_url(public_key, path=file_path)
        else:
            file_path = source_meta.get("path", "")
            if not file_path:
                raise ValueError("No file path in source metadata for Yandex Disk download")
            download_url = await client.get_download_url(file_path)

        logger.info(f"Downloading from Yandex Disk: {source_meta.get('name', file_path)}")

        # Download using the temporary URL (no special auth needed for temp URLs)
        success = await self._download_url(
            url=download_url,
            filepath=target_path,
            expected_size=source_meta.get("size"),
            description=f"Yandex Disk file: {source_meta.get('name', 'unknown')}",
        )

        if not success:
            raise RuntimeError(f"Failed to download from Yandex Disk: {source_meta.get('name', file_path)}")

        return DownloadResult(
            file_path=target_path,
            file_size=target_path.stat().st_size,
            metadata={
                "name": source_meta.get("name"),
                "path": file_path,
                "download_method": download_method,
            },
        )
