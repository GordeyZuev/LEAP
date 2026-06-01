"""Tests for the ``tv`` (token version) claim flowing through JWTHelper."""

import pytest

from api.auth.security import JWTHelper


@pytest.mark.unit
class TestTokenVersionClaim:
    """The ``tv`` claim must round-trip through encode → verify unchanged."""

    def test_access_token_carries_tv(self):
        token = JWTHelper.create_access_token({"user_id": "u1", "email": "a@b.c", "tv": 7})
        payload = JWTHelper.verify_token(token, token_type="access")
        assert payload is not None
        assert payload["tv"] == 7
        assert payload["type"] == "access"

    def test_refresh_token_carries_tv(self):
        token = JWTHelper.create_refresh_token({"user_id": "u1", "tv": 3})
        payload = JWTHelper.verify_token(token, token_type="refresh")
        assert payload is not None
        assert payload["tv"] == 3

    def test_missing_tv_is_none(self):
        """Tokens issued before the kill-switch (pre-022) lack ``tv``."""
        # Pretend a token was minted without the claim — server should treat
        # ``payload.get("tv")`` as None and reject.
        token = JWTHelper.create_access_token({"user_id": "u1", "email": "a@b.c"})
        payload = JWTHelper.verify_token(token, token_type="access")
        assert payload is not None
        assert payload.get("tv") is None

    def test_different_tv_values_produce_different_tokens(self):
        a = JWTHelper.create_access_token({"user_id": "u1", "email": "a@b.c", "tv": 0})
        b = JWTHelper.create_access_token({"user_id": "u1", "email": "a@b.c", "tv": 1})
        assert a != b
