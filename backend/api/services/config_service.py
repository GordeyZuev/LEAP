"""Service for user configurations and credentials"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.credential_service import CredentialService
from logger import get_logger

logger = get_logger()


class ConfigService:
    """Service for user configuration and credentials"""

    def __init__(self, session: AsyncSession, user_id: str):
        """Initialize config service."""
        self.session = session
        self.user_id = user_id
        self.cred_service = CredentialService(session)

    async def get_youtube_credentials(self) -> dict[str, Any]:
        """
        Get YouTube credentials for user.

        Returns:
            YouTube OAuth bundle

        Raises:
            ValueError: If credentials not found
        """
        return await self.cred_service.get_youtube_credentials(self.user_id)

    async def get_vk_credentials(self) -> dict[str, Any]:
        """
        Get VK credentials for user.

        Returns:
            VK credentials (access_token, group_id)

        Raises:
            ValueError: If credentials not found
        """
        return await self.cred_service.get_vk_credentials(self.user_id)
