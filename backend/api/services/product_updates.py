"""Small shared helpers for public product-news links and tokens."""

from __future__ import annotations

import hashlib
import hmac

from config.settings import get_settings


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def unsubscribe_token(subscription_id: str) -> str:
    secret = get_settings().security.jwt_secret_key.encode("utf-8")
    signature = hmac.new(secret, f"product-news:{subscription_id}".encode(), hashlib.sha256).hexdigest()
    return f"{subscription_id}.{signature}"


def verified_unsubscribe_id(token: str) -> str | None:
    subscription_id, separator, supplied = token.partition(".")
    if not separator or len(subscription_id) != 26:
        return None
    expected = unsubscribe_token(subscription_id).partition(".")[2]
    return subscription_id if hmac.compare_digest(supplied, expected) else None


def verified_subscription_id(token: str) -> str | None:
    """Validate a signed subscriber-management token."""
    return verified_unsubscribe_id(token)


def frontend_url(path: str) -> str:
    return f"{get_settings().email.base_url.rstrip('/')}{path}"
