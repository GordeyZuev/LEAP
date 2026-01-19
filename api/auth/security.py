"""Security utilities: password hashing, JWT tokens"""

from datetime import datetime, timedelta
from typing import Any

import bcrypt
import jwt

from config.settings import get_settings

settings = get_settings()


class PasswordHelper:
    """Password helper"""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash password using bcrypt.

        Args:
            password: Password in plain text

        Returns:
            Hashed password
        """
        salt = bcrypt.gensalt(rounds=settings.security.bcrypt_rounds)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify password.

        Args:
            plain_password: Password in plain text
            hashed_password: Hashed password

        Returns:
            True if password matches, otherwise False
        """
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False


class JWTHelper:
    """Helper for working with JWT tokens."""

    @staticmethod
    def create_access_token(subject: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """
        Create access token.

        Args:
            subject: Data to encode in token (usually {"user_id": 123})
            expires_delta: Token expiration time (default from settings)

        Returns:
            JWT token
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.security.jwt_access_token_expire_minutes)

        expire = datetime.utcnow() + expires_delta

        to_encode = subject.copy()
        to_encode.update({"exp": expire, "type": "access"})

        return jwt.encode(to_encode, settings.security.jwt_secret_key, algorithm=settings.security.jwt_algorithm)

    @staticmethod
    def create_refresh_token(subject: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """
        Create refresh token.

        Args:
            subject: Data to encode in token
            expires_delta: Token expiration time (default from settings)

        Returns:
            JWT token
        """
        if expires_delta is None:
            expires_delta = timedelta(days=settings.security.jwt_refresh_token_expire_days)

        expire = datetime.utcnow() + expires_delta

        to_encode = subject.copy()
        to_encode.update({"exp": expire, "type": "refresh"})

        return jwt.encode(to_encode, settings.security.jwt_secret_key, algorithm=settings.security.jwt_algorithm)

    @staticmethod
    def decode_token(token: str) -> dict[str, Any] | None:
        """
        Decode JWT token.

        Args:
            token: JWT token

        Returns:
            Decoded data or None if error
        """
        try:
            return jwt.decode(token, settings.security.jwt_secret_key, algorithms=[settings.security.jwt_algorithm])
        except Exception:
            return None

    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> dict[str, Any] | None:
        """
        Verify and decode token with type check.

        Args:
            token: JWT token
            token_type: Expected token type ("access" or "refresh")

        Returns:
            Decoded data or None if error
        """
        payload = JWTHelper.decode_token(token)
        if payload is None:
            return None

        if payload.get("type") != token_type:
            return None

        return payload
