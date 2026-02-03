"""User credentials encryption utilities"""

import base64
import json

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config.settings import get_settings

settings = get_settings()


class CredentialEncryption:
    """Encryption of user credentials."""

    def __init__(self):
        """Initialization of encryption."""
        # Use encryption_key if set, otherwise use JWT secret key
        encryption_key = settings.security.encryption_key or settings.security.jwt_secret_key
        self._fernet = self._create_fernet(encryption_key)

    def _create_fernet(self, secret: str) -> Fernet:
        """
        Creation of Fernet instance from secret key.
        """
        # Generate key from secret using PBKDF2HMAC
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"zoom_publishing_salt",  # In production use random salt
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return Fernet(key)

    def encrypt_credentials(self, credentials: dict) -> str:
        """
        Encryption of user credentials.
        """
        json_data = json.dumps(credentials)
        encrypted = self._fernet.encrypt(json_data.encode())
        return encrypted.decode()

    def decrypt_credentials(self, encrypted_data: str) -> dict:
        """
        Decryption of user credentials.
        """
        decrypted = self._fernet.decrypt(encrypted_data.encode())
        return json.loads(decrypted.decode())


# Singleton instance
_encryption = None


def get_encryption() -> CredentialEncryption:
    """
    Get singleton instance of encryption.
    """
    global _encryption
    if _encryption is None:
        _encryption = CredentialEncryption()
    return _encryption
