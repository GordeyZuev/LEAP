"""``get_current_user`` must reject tokens whose ``tv`` is stale."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.auth.dependencies import get_current_user
from api.auth.security import JWTHelper


def _request_with_bearer(token: str) -> MagicMock:
    req = MagicMock()
    req.headers = {"authorization": f"Bearer {token}"}
    req.cookies = {}
    req.state = MagicMock()
    return req


def _user(token_version: int = 0) -> MagicMock:
    u = MagicMock()
    u.id = "01HXXXXXXXXXXXXXXXXXXXXXXX"
    u.is_active = True
    u.token_version = token_version
    return u


@pytest.mark.unit
class TestGetCurrentUserTokenVersion:
    async def test_matching_tv_passes(self):
        user = _user(token_version=5)
        token = JWTHelper.create_access_token({"user_id": user.id, "email": "x@y.z", "tv": 5})

        with patch("api.auth.dependencies.UserRepository") as repo_cls:
            repo = repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=user)

            result = await get_current_user(request=_request_with_bearer(token), session=AsyncMock())

        assert result is user

    async def test_mismatched_tv_rejected_with_401(self):
        user = _user(token_version=5)
        # Token was minted before bump — has tv=4, user.token_version is now 5.
        token = JWTHelper.create_access_token({"user_id": user.id, "email": "x@y.z", "tv": 4})

        with patch("api.auth.dependencies.UserRepository") as repo_cls:
            repo = repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=user)

            with pytest.raises(HTTPException) as exc:
                await get_current_user(request=_request_with_bearer(token), session=AsyncMock())

        assert exc.value.status_code == 401
        assert "invalidated" in exc.value.detail.lower()

    async def test_missing_tv_claim_rejected(self):
        """Pre-022 tokens without the claim must fail closed."""
        user = _user(token_version=0)
        token = JWTHelper.create_access_token({"user_id": user.id, "email": "x@y.z"})  # no tv

        with patch("api.auth.dependencies.UserRepository") as repo_cls:
            repo = repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=user)

            with pytest.raises(HTTPException) as exc:
                await get_current_user(request=_request_with_bearer(token), session=AsyncMock())

        assert exc.value.status_code == 401
