"""Tests for Yandex Disk credential helper."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from api.services.yandex_disk_credentials import apply_yandex_disk_token_refresh, token_expires_within


@pytest.mark.unit
def test_token_expires_within_true() -> None:
    expiry = (datetime.now(UTC) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    assert token_expires_within(expiry, margin=300) is True


@pytest.mark.unit
def test_token_expires_within_false() -> None:
    expiry = (datetime.now(UTC) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert token_expires_within(expiry, margin=300) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_refresh_skips_without_refresh_token() -> None:
    creds = {"oauth_token": "x", "expiry": datetime.now(UTC).isoformat()}
    assert await apply_yandex_disk_token_refresh(creds) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_refresh_updates_credentials(mocker) -> None:
    expiry = (datetime.now(UTC) + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    creds = {
        "oauth_token": "old",
        "refresh_token": "rt",
        "client_id": "cid",
        "expiry": expiry,
    }
    mocker.patch(
        "api.services.yandex_disk_credentials.refresh_yandex_disk_oauth_token",
        new=AsyncMock(return_value={"access_token": "new", "expires_in": 3600}),
    )
    assert await apply_yandex_disk_token_refresh(creds) is True
    assert creds["oauth_token"] == "new"
