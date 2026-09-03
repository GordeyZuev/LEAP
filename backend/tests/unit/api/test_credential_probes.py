"""Credential connection checks: outcome classification per platform (mocked clients)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.mts_link_api import MtsLinkAuthenticationError, MtsLinkResponseError
from api.services.credential_probes import ProbeContext, check_credential
from api.zoom_api import ZoomAuthenticationError, ZoomResponseError
from yandex_disk_module.client import YandexDiskError


def _ctx(**creds) -> ProbeContext:
    return ProbeContext(credential_id=1, credentials=creds or {"api_token": "key-value"}, session=MagicMock())


@pytest.mark.unit
class TestUnsupportedPlatform:
    @pytest.mark.asyncio
    async def test_platform_without_probe_is_reported_not_guessed(self):
        """A platform with no check must not answer "ok" — that would be a false all-clear."""
        result = await check_credential(_ctx(), "assemblyai")

        assert result.status == "unsupported"
        assert "assemblyai" in result.detail


@pytest.mark.unit
class TestMtsLinkProbe:
    @pytest.mark.asyncio
    async def test_accepted_key_is_ok(self):
        api = AsyncMock()
        with patch("models.mts_link_auth.create_mts_link_client", return_value=api):
            result = await check_credential(_ctx(auth_type="api_key", api_token="org-key-value"), "mts_link")

        assert result.status == "ok"
        api.list_organization_members.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoked_key_asks_for_reauth(self):
        api = AsyncMock()
        api.list_organization_members.side_effect = MtsLinkAuthenticationError("Authentication failed (401)")
        with patch("models.mts_link_auth.create_mts_link_client", return_value=api):
            result = await check_credential(_ctx(auth_type="api_key", api_token="dead-key-value"), "mts_link")

        assert result.status == "auth_failed"

    @pytest.mark.asyncio
    async def test_provider_error_does_not_blame_the_key(self):
        api = AsyncMock()
        api.list_organization_members.side_effect = MtsLinkResponseError(500, "boom")
        with patch("models.mts_link_auth.create_mts_link_client", return_value=api):
            result = await check_credential(_ctx(auth_type="api_key", api_token="fine-key-value"), "mts_link")

        assert result.status == "unavailable"

    @pytest.mark.asyncio
    async def test_incomplete_blob_is_rejected(self):
        result = await check_credential(_ctx(auth_type="api_key"), "mts_link")

        assert result.status == "auth_failed"


@pytest.mark.unit
class TestZoomProbe:
    @pytest.mark.asyncio
    async def test_accepted_credentials_are_ok(self):
        api = AsyncMock()
        with (
            patch("models.zoom_auth.create_zoom_credentials", return_value=MagicMock()),
            patch("api.zoom_api.ZoomAPI", return_value=api),
        ):
            result = await check_credential(_ctx(account_id="a", client_id="b", client_secret="c"), "zoom")

        assert result.status == "ok"
        api.get_current_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejected_credentials_ask_for_reauth(self):
        api = AsyncMock()
        api.get_current_user.side_effect = ZoomAuthenticationError("Zoom rejected the credentials (401)")
        with (
            patch("models.zoom_auth.create_zoom_credentials", return_value=MagicMock()),
            patch("api.zoom_api.ZoomAPI", return_value=api),
        ):
            result = await check_credential(_ctx(account_id="a"), "zoom")

        assert result.status == "auth_failed"

    @pytest.mark.asyncio
    async def test_zoom_outage_is_unavailable(self):
        api = AsyncMock()
        api.get_current_user.side_effect = ZoomResponseError("API error: 503")
        with (
            patch("models.zoom_auth.create_zoom_credentials", return_value=MagicMock()),
            patch("api.zoom_api.ZoomAPI", return_value=api),
        ):
            result = await check_credential(_ctx(account_id="a"), "zoom")

        assert result.status == "unavailable"


@pytest.mark.unit
class TestYandexDiskProbe:
    @pytest.mark.asyncio
    async def test_valid_token_is_ok(self):
        client = AsyncMock()
        with (
            patch("api.services.yandex_disk_credentials.refresh_yandex_disk_credential_if_needed", new=AsyncMock()),
            patch("yandex_disk_module.client.YandexDiskClient", return_value=client),
        ):
            result = await check_credential(_ctx(oauth_token="y0_live"), "yandex_disk")

        assert result.status == "ok"
        client.get_disk_info.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_token_asks_for_reauth(self):
        client = AsyncMock()
        client.get_disk_info.side_effect = YandexDiskError("Unauthorized", 401)
        with (
            patch("api.services.yandex_disk_credentials.refresh_yandex_disk_credential_if_needed", new=AsyncMock()),
            patch("yandex_disk_module.client.YandexDiskClient", return_value=client),
        ):
            result = await check_credential(_ctx(oauth_token="y0_dead"), "yandex_disk")

        assert result.status == "auth_failed"

    @pytest.mark.asyncio
    async def test_server_error_is_unavailable(self):
        client = AsyncMock()
        client.get_disk_info.side_effect = YandexDiskError("Service unavailable", 503)
        with (
            patch("api.services.yandex_disk_credentials.refresh_yandex_disk_credential_if_needed", new=AsyncMock()),
            patch("yandex_disk_module.client.YandexDiskClient", return_value=client),
        ):
            result = await check_credential(_ctx(oauth_token="y0_live"), "yandex_disk")

        assert result.status == "unavailable"

    @pytest.mark.asyncio
    async def test_missing_token_is_rejected(self):
        with patch("api.services.yandex_disk_credentials.refresh_yandex_disk_credential_if_needed", new=AsyncMock()):
            result = await check_credential(_ctx(account="no token here"), "yandex_disk")

        assert result.status == "auth_failed"


@pytest.mark.unit
class TestProbeNeverRaises:
    @pytest.mark.asyncio
    async def test_unexpected_error_becomes_unavailable(self):
        """The endpoint must survive any client blowing up in a new way."""
        with patch("models.mts_link_auth.create_mts_link_client", side_effect=RuntimeError("boom")):
            result = await check_credential(_ctx(auth_type="api_key", api_token="any-key-value"), "mts_link")

        assert result.status == "unavailable"
        assert "RuntimeError" in result.detail
