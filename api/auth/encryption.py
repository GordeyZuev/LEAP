"""User credentials encryption (Zoom, YouTube, VK OAuth tokens).

Encryption: Fernet (AES-128-CBC + HMAC-SHA256).
Key: SECURITY_ENCRYPTION_KEY (required).
See docs/CREDENTIAL_SECURITY.md for details.
"""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from config.settings import get_settings


class CredentialEncryption:
    """Fernet-based credential encryption with dual-key rotation support."""

    def __init__(self) -> None:
        settings = get_settings()
        enc_key = settings.security.encryption_key
        if not enc_key:
            raise ValueError("SECURITY_ENCRYPTION_KEY is not set.")
        self._fernet = Fernet(enc_key.encode())

        old_key = settings.security.encryption_key_old
        self._fernet_old: Fernet | None = Fernet(old_key.encode()) if old_key else None

    def encrypt_credentials(self, credentials: dict[str, Any]) -> str:
        """Encrypt credentials with primary key."""
        return self._fernet.encrypt(json.dumps(credentials).encode()).decode()

    def decrypt_credentials(self, encrypted_data: str) -> dict[str, Any]:
        """Decrypt credentials. Tries primary key, then old key.

        Raises:
            ValueError: If decryption fails with all available keys.
        """
        for fernet in self._decryption_keys():
            try:
                return json.loads(fernet.decrypt(encrypted_data.encode()))
            except InvalidToken:
                continue

        raise ValueError(
            "Credentials could not be decrypted (encryption key may have changed). "
            "Please re-connect your account in Settings."
        )

    def needs_reencrypt(self, encrypted_data: str) -> bool:
        """True if primary key cannot decrypt (data is on old key)."""
        try:
            self._fernet.decrypt(encrypted_data.encode())
            return False
        except InvalidToken:
            return True

    def _decryption_keys(self) -> list[Fernet]:
        keys = [self._fernet]
        if self._fernet_old:
            keys.append(self._fernet_old)
        return keys


_encryption: CredentialEncryption | None = None


def get_encryption() -> CredentialEncryption:
    """Get singleton instance."""
    global _encryption
    if _encryption is None:
        _encryption = CredentialEncryption()
    return _encryption
