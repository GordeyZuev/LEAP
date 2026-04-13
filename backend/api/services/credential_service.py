"""User credentials service.

Handles credential retrieval with automatic lazy re-encryption
when legacy-format ciphertext is detected (key rotation support).
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.encryption import get_encryption
from api.repositories.auth_repos import UserCredentialRepository
from api.schemas.auth import UserCredentialInDB, UserCredentialUpdate
from logger import get_logger

logger = get_logger()


class CredentialService:
    """Service for working with credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserCredentialRepository(session)
        self.encryption = get_encryption()

    async def get_decrypted_credentials(
        self,
        user_id: str,
        platform: str,
        account_name: str | None = None,
        raise_if_not_found: bool = True,
    ) -> dict[str, Any] | None:
        """Get decrypted credentials for platform. Re-encrypts legacy data automatically.

        Raises:
            ValueError: If credentials not found (when raise_if_not_found=True)
                        or decryption fails.
        """
        credential = await self.repo.get_by_platform(user_id, platform, account_name)
        label = f"platform='{platform}'" + (f" account='{account_name}'" if account_name else "")

        if not credential:
            if raise_if_not_found:
                raise ValueError(f"Credentials for {label} not found for user {user_id}")
            return None

        if not credential.is_active:
            logger.warning(f"Inactive credentials | {label} user={user_id}")
            if raise_if_not_found:
                raise ValueError(f"Credentials for {label} are inactive")
            return None

        return await self._decrypt_and_reencrypt(credential)

    async def get_credentials_by_id(self, credential_id: int) -> dict[str, Any]:
        """Get decrypted credentials by ID. Re-encrypts legacy data automatically.

        Raises:
            ValueError: If credentials not found, inactive, or decryption fails.
        """
        credential = await self.repo.get_by_id(credential_id)

        if not credential:
            raise ValueError(f"Credential {credential_id} not found")

        if not credential.is_active:
            raise ValueError(f"Credential {credential_id} is inactive")

        return await self._decrypt_and_reencrypt(credential)

    async def get_youtube_credentials(self, user_id: str) -> dict[str, Any]:
        """Get YouTube OAuth credentials bundle.

        Raises:
            ValueError: If credentials not found or missing required fields.
        """
        creds = await self.get_decrypted_credentials(user_id, "youtube")
        if not creds:
            raise ValueError("YouTube credentials not found")

        if "client_secrets" not in creds and "token" not in creds:
            raise ValueError("YouTube credentials missing client_secrets or token")

        return creds

    async def get_vk_credentials(self, user_id: str) -> dict[str, Any]:
        """Get VK credentials.

        Raises:
            ValueError: If credentials not found or missing access_token.
        """
        creds = await self.get_decrypted_credentials(user_id, "vk")
        if not creds:
            raise ValueError("VK credentials not found")

        if "access_token" not in creds:
            raise ValueError("VK credentials missing access_token")

        return creds

    async def _decrypt_and_reencrypt(self, credential: UserCredentialInDB) -> dict[str, Any]:
        """Decrypt credential and lazily re-encrypt if using legacy format."""
        try:
            decrypted = self.encryption.decrypt_credentials(credential.encrypted_data)
        except ValueError as e:
            logger.error(f"Decrypt failed | credential={credential.id} platform={credential.platform}: {e}")
            raise

        if self.encryption.needs_reencrypt(credential.encrypted_data):
            await self._reencrypt(credential.id, decrypted)

        return decrypted

    async def _reencrypt(self, credential_id: int, plaintext: dict[str, Any]) -> None:
        """Re-encrypt credential with current primary key."""
        try:
            new_encrypted = self.encryption.encrypt_credentials(plaintext)
            await self.repo.update(credential_id, UserCredentialUpdate(encrypted_data=new_encrypted))
            logger.info(f"Lazy re-encrypted credential | id={credential_id}")
        except Exception as e:
            logger.warning(f"Lazy re-encrypt failed | id={credential_id}: {e}")
