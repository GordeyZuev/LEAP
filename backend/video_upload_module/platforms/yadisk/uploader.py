"""Yandex Disk uploader -- uploads processed video files to Yandex Disk."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from api.services.oauth_service import refresh_yandex_disk_oauth_token
from logger import get_logger
from video_upload_module.core.base import BaseUploader, UploadResult
from yandex_disk_module.client import YandexDiskClient, YandexDiskError

if TYPE_CHECKING:
    from video_upload_module.credentials_provider import DatabaseCredentialProvider

logger = get_logger()


def _expiry_is_nearing(expiry_str: str | None, *, margin_seconds: int = 300) -> bool:
    if not expiry_str:
        return False
    try:
        normalized = expiry_str.replace("Z", "+00:00") if expiry_str.endswith("Z") else expiry_str
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return datetime.now(UTC) >= dt - timedelta(seconds=margin_seconds)
    except ValueError:
        return False


class YandexDiskUploader(BaseUploader):
    """Uploads video files to Yandex Disk via REST API."""

    def __init__(
        self,
        config,
        oauth_token: str | None = None,
        *,
        credential_provider: DatabaseCredentialProvider | None = None,
        credentials_data: dict[str, Any] | None = None,
    ):
        super().__init__(config)
        self.oauth_token = oauth_token
        self.credential_provider = credential_provider
        self.credentials_data = credentials_data

    async def _try_refresh_token(self) -> bool:
        """Refresh OAuth token using stored refresh_token and app credentials."""
        if not self.credential_provider or not self.credentials_data:
            return False
        rt = self.credentials_data.get("refresh_token")
        cid = self.credentials_data.get("client_id")
        if not rt or not cid:
            logger.warning("Yandex Disk token refresh skipped: missing refresh_token or client_id")
            return False
        try:
            token_data = await refresh_yandex_disk_oauth_token(
                rt,
                override_client_id=cid,
                override_client_secret=self.credentials_data.get("client_secret"),
            )
        except Exception as e:
            logger.error(f"Yandex Disk token refresh failed: {e}")
            return False
        self.credentials_data["oauth_token"] = token_data["access_token"]
        self.oauth_token = self.credentials_data["oauth_token"]
        if token_data.get("refresh_token"):
            self.credentials_data["refresh_token"] = token_data["refresh_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self.credentials_data["expires_in"] = expires_in
        self.credentials_data["expiry"] = (
            (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat().replace("+00:00", "Z")
        )
        if not await self.credential_provider.save_credentials(self.credentials_data):
            logger.error("Yandex Disk: failed to persist refreshed credentials")
            return False
        logger.info("Yandex Disk OAuth token refreshed and saved")
        return True

    async def _maybe_refresh_before_request(self) -> None:
        if (
            self.credential_provider
            and self.credentials_data
            and _expiry_is_nearing(self.credentials_data.get("expiry"))
        ):
            await self._try_refresh_token()

    async def authenticate(self) -> bool:
        """Verify OAuth token by checking disk info."""
        if not self.oauth_token:
            logger.error("No OAuth token for Yandex Disk")
            return False

        await self._maybe_refresh_before_request()
        client = YandexDiskClient(oauth_token=self.oauth_token)
        try:
            await client.get_disk_info()
            self._authenticated = True
            return True
        except YandexDiskError as e:
            if e.status_code == 401 and await self._try_refresh_token():
                try:
                    client = YandexDiskClient(oauth_token=self.oauth_token)
                    await client.get_disk_info()
                    self._authenticated = True
                    return True
                except YandexDiskError as e2:
                    logger.error(f"Yandex Disk authentication failed after refresh: {e2}")
                    return False
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
            publish: If True, publish file and set video_url to public link
        """
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
        publish = kwargs.get("publish", False)
        disk_path = f"{folder_path.rstrip('/')}/{filename}"

        await self._maybe_refresh_before_request()
        client = YandexDiskClient(oauth_token=self.oauth_token)

        try:
            return await self._do_upload(
                client, local_path, disk_path, folder_path, filename, overwrite, publish, title
            )
        except YandexDiskError as e:
            if e.status_code == 401 and await self._try_refresh_token():
                client = YandexDiskClient(oauth_token=self.oauth_token)
                try:
                    return await self._do_upload(
                        client, local_path, disk_path, folder_path, filename, overwrite, publish, title
                    )
                except YandexDiskError as e2:
                    logger.error(f"Yandex Disk upload failed after refresh: {e2}")
                    return UploadResult(
                        video_id="",
                        video_url="",
                        title=title,
                        upload_time=datetime.now(),
                        status="failed",
                        platform="yandex_disk",
                        error_message=str(e2),
                    )
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

    async def _do_upload(
        self,
        client: YandexDiskClient,
        local_path: Path,
        disk_path: str,
        folder_path: str,
        filename: str,
        overwrite: bool,
        publish: bool,
        title: str,
    ) -> UploadResult:
        success = await client.upload_file(
            local_path=local_path,
            disk_path=disk_path,
            overwrite=overwrite,
        )

        if not success:
            return UploadResult(
                video_id="",
                video_url="",
                title=title,
                upload_time=datetime.now(),
                status="failed",
                platform="yandex_disk",
                error_message="Upload returned False",
            )

        video_url = f"disk:{disk_path}"
        extra_meta: dict[str, Any] = {
            "disk_path": disk_path,
            "folder_path": folder_path,
            "filename": filename,
        }
        if publish:
            try:
                video_url = await client.publish_resource(disk_path)
                extra_meta["published"] = True
                extra_meta["public_url"] = video_url
            except Exception as e:
                logger.error(f"Yandex Disk publish failed: {e}")
                return UploadResult(
                    video_id=disk_path,
                    video_url=f"disk:{disk_path}",
                    title=title,
                    upload_time=datetime.now(),
                    status="failed",
                    platform="yandex_disk",
                    error_message=f"Upload succeeded but publish failed: {e}",
                    metadata=extra_meta,
                )

        return self._create_result(
            video_id=disk_path,
            video_url=video_url,
            title=title,
            platform="yandex_disk",
            metadata=extra_meta,
        )

    async def get_video_info(self, video_id: str) -> dict[str, Any] | None:
        """Get file info from Yandex Disk. video_id is the disk path."""
        client = YandexDiskClient(oauth_token=self.oauth_token)
        try:
            return await client.get_resource_meta(video_id)
        except YandexDiskError:
            return None

    async def delete_video(self, video_id: str) -> bool:
        """Delete file from Yandex Disk. video_id is the disk path."""
        client = YandexDiskClient(oauth_token=self.oauth_token)
        try:
            await client.delete_resource(video_id, permanently=False)
            return True
        except YandexDiskError:
            return False
