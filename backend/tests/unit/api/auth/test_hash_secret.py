"""Tests for SHA-256 hashing of auth secrets at rest."""

import hashlib

import pytest

from api.auth.security import hash_secret
from api.routers.oauth import _require_oauth_state_platform


@pytest.mark.unit
def test_hash_secret_is_sha256_hex():
    raw = "refresh-jwt-value"
    assert hash_secret(raw) == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert hash_secret(raw) != raw
    assert len(hash_secret(raw)) == 64


@pytest.mark.unit
def test_oauth_state_platform_must_match():
    _require_oauth_state_platform({"platform": "youtube", "user_id": "u1"}, "youtube")
    with pytest.raises(ValueError):
        _require_oauth_state_platform({"platform": "zoom", "user_id": "u1"}, "youtube")
    with pytest.raises(ValueError):
        _require_oauth_state_platform({"user_id": "u1"}, "youtube")
