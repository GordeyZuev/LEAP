"""Universal upload manager for multiple platforms."""

import asyncio

from logger import get_logger

from ..config_factory import UploadConfig
from ..platforms.vk import VKUploader
from ..platforms.youtube import YouTubeUploader
from .base import BaseUploader, UploadResult

logger = get_logger()


class UploadManager:
    """Multi-platform video upload manager."""

    def __init__(self, config: UploadConfig):
        self.config = config
        self.uploaders: dict[str, BaseUploader] = {}
        self._initialize_uploaders()

    def _initialize_uploaders(self):
        """Initialize uploaders for configured platforms."""
        if self.config.youtube:
            self.uploaders["youtube"] = YouTubeUploader(self.config.youtube)
        if self.config.vk:
            self.uploaders["vk"] = VKUploader(self.config.vk)

    def add_uploader(self, platform: str, uploader: BaseUploader):
        """Add uploader for a platform."""
        self.uploaders[platform] = uploader

    def get_uploader(self, platform: str) -> BaseUploader | None:
        """Get uploader by platform name."""
        return self.uploaders.get(platform)

    def get_available_platforms(self) -> list[str]:
        """Get list of available platforms."""
        return list(self.uploaders.keys())

    async def upload_to_platform(
        self,
        platform: str,
        video_path: str,
        title: str,
        description: str = "",
        progress=None,
        task_id=None,
        **kwargs,
    ) -> UploadResult | None:
        """Upload video to specific platform."""

        uploader = self.get_uploader(platform)
        if not uploader:
            logger.error(f"Uploader for platform {platform} not found")
            return None

        is_valid, message = uploader.validate_file(video_path)
        if not is_valid:
            logger.error(f"File validation failed: {message}")
            return None

        for attempt in range(self.config.retry_attempts):
            try:
                logger.info(f"Upload attempt {attempt + 1}/{self.config.retry_attempts} to {platform}")

                result = await uploader.upload_video(
                    video_path=video_path,
                    title=title,
                    description=description,
                    progress=progress,
                    task_id=task_id,
                    **kwargs,
                )

                if result:
                    return result

            except Exception as e:
                logger.error(f"Upload error to {platform} (attempt {attempt + 1}): {e}")

                if attempt < self.config.retry_attempts - 1:
                    logger.info(f"Waiting {self.config.retry_delay} seconds before retry...")
                    await asyncio.sleep(self.config.retry_delay)

        logger.error(f"Failed to upload video to {platform} after {self.config.retry_attempts} attempts")
        return None

    async def upload_caption(
        self,
        platform: str,
        video_id: str,
        caption_path: str,
        language: str = "ru",
        name: str | None = None,
    ) -> bool:
        """Upload captions if platform supports it."""
        uploader = self.get_uploader(platform)
        if not uploader:
            logger.error(f"Uploader for platform {platform} not found")
            return False

        if not hasattr(uploader, "upload_caption"):
            logger.info(f"Platform {platform} does not support caption upload")
            return False

        try:
            return bool(
                await uploader.upload_caption(
                    video_id=video_id,
                    caption_path=caption_path,
                    language=language,
                    name=name,
                )
            )
        except Exception as e:
            logger.error(f"Caption upload error to {platform}: {e}")
            return False
