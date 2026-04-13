"""Factory functions for creating uploaders with database credentials."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.encryption import get_encryption
from api.repositories.auth_repos import UserCredentialRepository
from logger import get_logger

from .config_factory import VKUploadConfig, YouTubeUploadConfig
from .credentials_provider import DatabaseCredentialProvider
from .platforms.vk.uploader import VKUploader
from .platforms.yadisk.uploader import YandexDiskUploader
from .platforms.youtube.uploader import YouTubeUploader

logger = get_logger()


async def create_youtube_uploader_from_db(
    credential_id: int,
    session: AsyncSession,
    youtube_config: YouTubeUploadConfig | None = None,
) -> YouTubeUploader:
    """Create YouTubeUploader with database credentials."""
    if not youtube_config:
        youtube_config = YouTubeUploadConfig(enabled=True, client_secrets_file="", credentials_file="")

    encryption = get_encryption()
    repo = UserCredentialRepository(session)

    credential_provider = DatabaseCredentialProvider(
        credential_id=credential_id,
        encryption_service=encryption,
        credential_repository=repo,
    )

    uploader = YouTubeUploader(config=youtube_config, credential_provider=credential_provider)

    logger.info(f"Created YouTubeUploader with DB credential ID: {credential_id}")
    return uploader


async def create_vk_uploader_from_db(
    credential_id: int,
    session: AsyncSession,
    vk_config: VKUploadConfig | None = None,
) -> VKUploader:
    """Create VKUploader with database credentials."""
    encryption = get_encryption()
    repo = UserCredentialRepository(session)

    credential_provider = DatabaseCredentialProvider(
        credential_id=credential_id,
        encryption_service=encryption,
        credential_repository=repo,
    )

    if not vk_config:
        vk_config = VKUploadConfig(enabled=True)

    uploader = VKUploader(config=vk_config, credential_provider=credential_provider)

    logger.info(f"Created VKUploader with DB credential ID: {credential_id}")
    return uploader


async def create_yadisk_uploader_from_db(
    credential_id: int,
    session: AsyncSession,
) -> YandexDiskUploader:
    """Create YandexDiskUploader with database credentials."""
    encryption = get_encryption()
    repo = UserCredentialRepository(session)
    credential = await repo.get_by_id(credential_id)

    if not credential:
        raise ValueError(f"Credential {credential_id} not found")

    credentials_data = encryption.decrypt_credentials(credential.encrypted_data)
    oauth_token = credentials_data.get("oauth_token")

    if not oauth_token:
        raise ValueError(f"No oauth_token in credential {credential_id}")

    uploader = YandexDiskUploader(config=None, oauth_token=oauth_token)

    logger.info(f"Created YandexDiskUploader with DB credential ID: {credential_id}")
    return uploader


async def create_uploader_from_db(
    platform: str,
    credential_id: int,
    session: AsyncSession,
    config: Any | None = None,
) -> YouTubeUploader | VKUploader | YandexDiskUploader:
    """Create platform uploader with database credentials."""
    if platform == "youtube":
        return await create_youtube_uploader_from_db(credential_id, session, config)
    if platform in ("vk", "vk_video"):
        return await create_vk_uploader_from_db(credential_id, session, config)
    if platform == "yandex_disk":
        return await create_yadisk_uploader_from_db(credential_id, session)
    raise ValueError(f"Unsupported platform: {platform}")
