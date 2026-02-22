"""Factory for creating platform uploaders with user credentials."""

import json
import tempfile
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.config_service import ConfigService
from logger import get_logger

from .config_factory import VKConfig, YouTubeConfig
from .platforms.vk.uploader import VKUploader
from .platforms.youtube.uploader import YouTubeUploader

logger = get_logger()


class UploaderFactory:
    """Factory for creating platform uploaders."""

    @staticmethod
    async def create_youtube_uploader(
        session: AsyncSession, user_id: str, credential_id: int | None = None
    ) -> YouTubeUploader:
        """Create YouTubeUploader for user."""
        config_helper = ConfigService(session, user_id)

        if credential_id:
            creds = await config_helper.cred_service.get_credentials_by_id(credential_id)
        else:
            creds = await config_helper.get_youtube_credentials()

        temp_dir = Path(tempfile.gettempdir()) / f"youtube_creds_user_{user_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        client_secrets_file = temp_dir / "client_secrets.json"
        credentials_file = temp_dir / "credentials.json"

        if "client_secrets" in creds:
            with client_secrets_file.open("w", encoding="utf-8") as f:
                json.dump(creds["client_secrets"], f, ensure_ascii=False, indent=2)

        if "token" in creds:
            with credentials_file.open("w", encoding="utf-8") as f:
                json.dump(creds, f, ensure_ascii=False, indent=2)

        config = YouTubeConfig(
            client_secrets_file=str(client_secrets_file),
            credentials_file=str(credentials_file),
            scopes=creds.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"]),
            playlist_id=creds.get("playlist_id"),
            default_privacy=creds.get("default_privacy", "unlisted"),
            default_category=creds.get("default_category", "22"),
        )

        logger.info(f"Created YouTubeUploader for user {user_id}")
        return YouTubeUploader(config)

    @staticmethod
    async def create_vk_uploader(session: AsyncSession, user_id: str, credential_id: int | None = None) -> VKUploader:
        """Create VKUploader for user."""
        config_helper = ConfigService(session, user_id)

        if credential_id:
            creds = await config_helper.cred_service.get_credentials_by_id(credential_id)
        else:
            creds = await config_helper.get_vk_credentials()

        config = VKConfig(
            access_token=creds["access_token"],
            group_id=creds.get("group_id"),
            album_id=creds.get("album_id"),
            app_id=creds.get("app_id", "54249533"),
            scope=creds.get("scope", "video,groups,wall"),
        )

        logger.info(f"Created VKUploader for user {user_id}")
        return VKUploader(config)

    @staticmethod
    async def create_uploader(
        session: AsyncSession,
        user_id: str,
        platform: Literal["youtube", "vk"],
        credential_id: int | None = None,
    ) -> YouTubeUploader | VKUploader:
        """Create uploader for any platform."""
        if platform == "youtube":
            return await UploaderFactory.create_youtube_uploader(session, user_id, credential_id)
        if platform == "vk":
            return await UploaderFactory.create_vk_uploader(session, user_id, credential_id)
        raise ValueError(f"Unsupported platform: {platform}")

    @staticmethod
    async def create_uploader_by_preset_id(
        session: AsyncSession, user_id: str, preset_id: int
    ) -> YouTubeUploader | VKUploader:
        """Create uploader from output preset."""
        from api.repositories.template_repos import OutputPresetRepository

        preset_repo = OutputPresetRepository(session)
        preset = await preset_repo.find_by_id(preset_id, user_id)

        if not preset:
            raise ValueError(f"Output preset {preset_id} not found for user {user_id}")

        if not preset.credential_id:
            raise ValueError(f"Output preset {preset_id} has no credential configured")

        platform_map = {
            "YOUTUBE": "youtube",
            "VK": "vk",
        }

        platform = platform_map.get(preset.platform.upper())
        if not platform:
            raise ValueError(f"Unsupported platform in preset: {preset.platform}")

        return await UploaderFactory.create_uploader(
            session=session, user_id=user_id, platform=platform, credential_id=preset.credential_id
        )
