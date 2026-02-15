"""User credentials service.

Provides convenient interface for retrieving decrypted credentials
and using them in API requests to external services.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.encryption import get_encryption
from api.repositories.auth_repos import UserCredentialRepository
from logger import get_logger

logger = get_logger()


class CredentialService:
    """Service for working with credentials."""

    def __init__(self, session: AsyncSession):
        """Initialize service."""
        self.session = session
        self.repo = UserCredentialRepository(session)
        self.encryption = get_encryption()

    async def get_decrypted_credentials(
        self, user_id: str, platform: str, account_name: str | None = None, raise_if_not_found: bool = True
    ) -> dict[str, Any] | None:
        """
        Get decrypted credentials for platform.

        Args:
            user_id: User ID
            platform: Platform (zoom, youtube, vk, etc)
            account_name: Account name (for multiple accounts on one platform)
            raise_if_not_found: Raise error if not found

        Returns:
            Decrypted credentials or None

        Raises:
            ValueError: If credentials not found (when raise_if_not_found=True)
        """
        credential = await self.repo.get_by_platform(user_id, platform, account_name)

        if not credential:
            account_str = f" (account: {account_name})" if account_name else ""
            if raise_if_not_found:
                raise ValueError(f"Credentials for platform '{platform}'{account_str} not found for user {user_id}")
            return None

        if not credential.is_active:
            account_str = f" (account: {account_name})" if account_name else ""
            logger.warning(f"Credentials for platform '{platform}'{account_str} are inactive for user {user_id}")
            if raise_if_not_found:
                raise ValueError(f"Credentials for platform '{platform}'{account_str} are inactive")
            return None

        try:
            decrypted = self.encryption.decrypt_credentials(credential.encrypted_data)
            account_str = f" (account: {account_name})" if account_name else ""
            logger.debug(
                f"Successfully decrypted credentials for platform '{platform}'{account_str} for user {user_id}"
            )
            return decrypted
        except Exception as e:
            logger.error(f"Failed to decrypt credentials for platform '{platform}': {e}")
            raise ValueError(f"Failed to decrypt credentials: {e}") from e

    async def get_credentials_by_id(self, credential_id: int) -> dict[str, Any]:
        """
        Get decrypted credentials by ID.

        Args:
            credential_id: Credential ID

        Returns:
            Decrypted credentials

        Raises:
            ValueError: If credentials not found or invalid
        """
        credential = await self.repo.get_by_id(credential_id)

        if not credential:
            raise ValueError(f"Credential {credential_id} not found")

        if not credential.is_active:
            raise ValueError(f"Credential {credential_id} is inactive")

        try:
            decrypted = self.encryption.decrypt_credentials(credential.encrypted_data)
            logger.debug(f"Successfully decrypted credential {credential_id} (platform: {credential.platform})")
            return decrypted
        except Exception as e:
            logger.error(f"Failed to decrypt credential {credential_id}: {e}")
            raise ValueError(f"Failed to decrypt credential: {e}") from e

    async def get_youtube_credentials(self, user_id: str) -> dict[str, Any]:
        """
        Get YouTube credentials (OAuth bundle).

        Args:
            user_id: User ID

        Returns:
            Full OAuth bundle (client_secrets, token, scopes)

        Raises:
            ValueError: If credentials not found or invalid
        """
        creds = await self.get_decrypted_credentials(user_id, "youtube")
        if not creds:
            raise ValueError("YouTube credentials not found")

        # YouTube stores the whole bundle as-is
        # Check for client_secrets or token
        if "client_secrets" not in creds and "token" not in creds:
            raise ValueError("YouTube credentials missing client_secrets or token")

        return creds

    async def get_vk_credentials(self, user_id: str) -> dict[str, Any]:
        """
        Get VK credentials.

        Args:
            user_id: User ID

        Returns:
            Dict with access_token and optionally group_id

        Raises:
            ValueError: If credentials not found or invalid
        """
        creds = await self.get_decrypted_credentials(user_id, "vk")
        if not creds:
            raise ValueError("VK credentials not found")

        if "access_token" not in creds:
            raise ValueError("VK credentials missing access_token")

        return creds
