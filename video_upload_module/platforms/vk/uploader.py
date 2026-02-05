"""VK video uploader implementation."""

import asyncio
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx

from logger import get_logger

from ...config_factory import VKConfig
from ...core.base import BaseUploader, UploadResult
from ..youtube.token_handler import TokenRefreshError, requires_valid_vk_token

logger = get_logger()


class VKUploader(BaseUploader):
    """VK video uploader."""

    def __init__(self, config: VKConfig, credential_provider=None):
        super().__init__(config)
        self.config = config
        self.credential_provider = credential_provider
        self.base_url = "https://api.vk.com/method"
        self._authenticated = False

    async def authenticate(self) -> bool:
        """Authenticate with VK API."""
        if self.credential_provider:
            return await self._authenticate_with_provider()

        return await self._authenticate_legacy()

    async def _authenticate_with_provider(self) -> bool:
        """Authenticate using credential provider (DB mode)."""
        try:
            if hasattr(self.credential_provider, "get_vk_credentials"):
                creds = await self.credential_provider.get_vk_credentials()
            else:
                creds = await self.credential_provider.load_credentials()

            if not creds:
                logger.error("No VK credentials found in database")
                return False

            access_token = creds.get("access_token")
            expiry_str = creds.get("expiry")

            if not access_token:
                logger.error("No access_token in VK credentials")
                return False

            needs_refresh = False
            if expiry_str:
                try:
                    from datetime import datetime

                    expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    now = datetime.now(UTC)
                    if expiry <= now or (expiry - now).total_seconds() < 300:
                        needs_refresh = True
                        logger.info("VK token expired or expiring soon, refreshing...")
                except Exception as e:
                    logger.warning(f"Failed to parse expiry: {e}")

            if needs_refresh and creds.get("refresh_token"):
                if hasattr(self.credential_provider, "refresh_vk_token"):
                    refreshed = await self.credential_provider.refresh_vk_token()
                    if refreshed:
                        access_token = refreshed.get("access_token")
                        logger.info("VK token refreshed successfully")
                    else:
                        logger.error("Failed to refresh VK token, using existing (may fail)")
                else:
                    logger.warning("Credential provider doesn't support VK refresh")

            self.config.access_token = access_token
            return await self._validate_token()

        except Exception as e:
            logger.error(f"Error authenticating with credential provider: {e}")
            return False

    async def _authenticate_legacy(self) -> bool:
        """Legacy file-based authentication mode."""
        if not self.config.access_token:
            logger.error(
                "VK access_token not found. Use OAuth 2.0 flow via API (GET /oauth/vk/authorize) to obtain credentials."
            )
            return False

        return await self._validate_token()

    async def _validate_token(self) -> bool:
        """Validate VK access token."""
        try:
            async with httpx.AsyncClient() as client:
                params = {"access_token": self.config.access_token, "v": "5.131"}
                response = await client.post(f"{self.base_url}/users.get", data=params)

                if response.status_code == 200:
                    data = response.json()
                    if "error" in data:
                        error_info = data["error"]
                        error_code = error_info.get("error_code")
                        error_msg = error_info.get("error_msg", "Unknown error")

                        # Token errors are expected, not critical
                        if error_code in (5, 28):
                            logger.warning(f"VK token invalid or expired: {error_msg}")
                        else:
                            logger.error(f"VK API Error [{error_code}]: {error_msg}")
                        return False
                    self._authenticated = True
                    logger.info("VK authentication successful")
                    return True
                logger.warning(f"VK API HTTP error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"VK token validation exception: {e}")
            return False

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        album_id: str | None = None,
        thumbnail_path: str | None = None,
        progress=None,
        task_id=None,
        **kwargs,
    ) -> UploadResult | None:
        """Upload video to VK with metadata and optional thumbnail."""

        if not self._authenticated:
            if not await self.authenticate():
                return None

        try:
            logger.info(f"Uploading video to VK: {title}")

            upload_url = await self._get_upload_url(title, description, album_id, **kwargs)
            if not upload_url:
                logger.error("Failed to get upload URL")
                return None

            upload_result = await self._upload_video_file(upload_url, video_path, progress, task_id)
            if not upload_result:
                logger.error("File upload error")
                return None

            video_id = upload_result.get("video_id")
            owner_id = upload_result.get("owner_id")

            if video_id and owner_id:
                video_url = f"https://vk.com/video{owner_id}_{video_id}"

                logger.info(f"Video uploaded: {video_url}")

                result = self._create_result(video_id=video_id, video_url=video_url, title=title, platform="vk")
                result.metadata["owner_id"] = owner_id

                # If album_id provided, video was added to album
                if album_id:
                    result.metadata["album_id"] = album_id
                    result.metadata["added_to_album"] = True
                    logger.info(f"Video added to album: {album_id}")

                if thumbnail_path and Path(thumbnail_path).exists():
                    try:
                        from .thumbnail_manager import VKThumbnailManager

                        thumbnail_manager = VKThumbnailManager(self.config)
                        await asyncio.sleep(2)
                        success = await thumbnail_manager.set_video_thumbnail(video_id, owner_id, thumbnail_path)
                        if success:
                            result.metadata["thumbnail_set"] = True
                            logger.info(f"Thumbnail set for video {video_id}")
                        else:
                            result.metadata["thumbnail_error"] = "Failed to set thumbnail"
                    except Exception as e:
                        logger.warning(f"Failed to set thumbnail: {e}")
                        result.metadata["thumbnail_error"] = str(e)

                return result
            logger.error("Failed to get video ID after upload")
            return None

        except Exception as e:
            logger.error(f"VK video upload error: {e}")
            return None

    async def get_video_info(self, video_id: str) -> dict[str, Any] | None:
        """Get video information."""
        if not self._authenticated:
            return None

        params = {
            "videos": video_id,
            "extended": 1,
        }

        try:
            response = await asyncio.wait_for(self._make_request("video.get", params), timeout=30.0)

            if response and "items" in response and response["items"]:
                video = response["items"][0]
                return {
                    "title": video.get("title", ""),
                    "description": video.get("description", ""),
                    "duration": video.get("duration", 0),
                    "views": video.get("views", 0),
                    "date": video.get("date", 0),
                    "privacy_view": video.get("privacy_view", 0),
                    "privacy_comment": video.get("privacy_comment", 0),
                }

            return None

        except TimeoutError:
            logger.error(f"Timeout getting video info for {video_id}")
            return None

    async def delete_video(self, video_id: str) -> bool:
        """Delete video."""
        if not self._authenticated:
            return False

        params = {
            "video_id": video_id,
            "owner_id": None,
        }

        try:
            response = await asyncio.wait_for(self._make_request("video.delete", params), timeout=30.0)

            if response:
                logger.info(f"Video deleted: {video_id}")
                return True
            logger.error(f"Video deletion error: {video_id}")
            return False

        except TimeoutError:
            logger.error(f"Timeout deleting video {video_id}")
            return False

    async def _get_upload_url(self, name: str, description: str = "", album_id: str | None = None, **kwargs) -> str:
        """Get video upload URL."""
        params = {
            "name": name,
            "description": description,
            "privacy_view": kwargs.get("privacy_view", self.config.privacy_view),
            "privacy_comment": kwargs.get("privacy_comment", self.config.privacy_comment),
            "no_comments": int(kwargs.get("no_comments", self.config.no_comments)),
            "repeat": int(kwargs.get("repeat", self.config.repeat)),
        }

        group_id = kwargs.get("group_id", self.config.group_id)
        if group_id:
            params["group_id"] = group_id

        target_album_id = album_id or kwargs.get("album_id", self.config.album_id)
        if target_album_id:
            params["album_id"] = target_album_id

        if "wallpost" in kwargs:
            params["wallpost"] = int(kwargs["wallpost"])
            logger.debug(f"Wallpost enabled: {kwargs['wallpost']}")

        try:
            response = await asyncio.wait_for(self._make_request("video.save", params), timeout=30.0)

            if response and "upload_url" in response:
                return response["upload_url"]

            return None

        except TimeoutError:
            logger.error("Timeout getting upload URL")
            return None

    async def _upload_video_file(
        self, upload_url: str, video_path: str, progress=None, task_id=None
    ) -> dict[str, Any] | None:
        """Upload video file to VK using streaming for large files."""
        try:
            file_size = Path(video_path).stat().st_size
            logger.info(f"Uploading video file: {Path(video_path).name} ({file_size / (1024**2):.1f} MB)")

            # Dynamic timeout based on file size: 10 min base + 2 min per GB
            timeout_seconds = 600 + (file_size // (1024**3)) * 120
            timeout = httpx.Timeout(timeout_seconds, read=300.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                with Path(video_path).open("rb") as video_file:
                    files = {"video_file": (Path(video_path).name, video_file)}

                    response = await client.post(upload_url, files=files)

                    if response.status_code == 200:
                        result_data = response.json()

                        if "error" in result_data:
                            logger.error(f"VK Upload Error: {result_data['error']}")
                            return None

                        if progress and task_id is not None:
                            try:
                                if task_id in progress.task_ids:
                                    progress.update(task_id, completed=100, total=100)
                            except Exception as e:
                                logger.warning(f"Progress update failed: {e}")

                        logger.info(f"Video uploaded successfully: video_id={result_data.get('video_id')}")
                        return result_data

                    error_text = response.text
                    logger.error(f"VK upload failed: HTTP {response.status_code}, {error_text[:200]}")
                    return None

        except httpx.TimeoutException:
            logger.error(f"Upload timeout after {timeout_seconds}s for file {Path(video_path).name}")
            return None
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return None

    @requires_valid_vk_token(max_retries=1)
    async def _make_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Execute VK API request with automatic token refresh."""
        params["access_token"] = self.config.access_token
        params["v"] = "5.131"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/{method}", data=params)

                if response.status_code == 200:
                    data = response.json()

                    # Return full response to allow decorator to check for token errors
                    if "error" in data:
                        error_info = data["error"]
                        error_code = error_info.get("error_code")

                        # Token errors - let decorator handle them
                        if error_code in (5, 28):
                            return data

                        # Other errors
                        logger.error(f"VK API Error: {error_info}")
                        return None

                    return data.get("response")

                error_text = response.text
                logger.error(f"HTTP Error: {response.status_code}, Response: {error_text[:500]}")
                return None
        except TokenRefreshError:
            raise
        except Exception as e:
            logger.error(f"VK API request error: {e}")
            return None
