"""Unit tests for MTS Link UserAPI client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.mts_link_api import (
    MtsLinkAPI,
    MtsLinkAPIError,
    MtsLinkAuthenticationError,
    MtsLinkConversionBusyError,
    extract_download_url,
    pick_active_conversion,
    unwrap_conversion_jobs,
    unwrap_items,
)


def _mock_http(response):
    """AsyncClient stub whose ``request`` returns ``response``."""
    http = AsyncMock()
    http.request = AsyncMock(return_value=response)
    http.__aenter__ = AsyncMock(return_value=http)
    http.__aexit__ = AsyncMock(return_value=None)
    return http


def _error_response(status_code: int, message: str):
    response = MagicMock()
    response.status_code = status_code
    response.text = message
    response.json.return_value = {"error": {"message": message}}
    return response


@pytest.mark.unit
class TestMtsLinkAPI:
    def test_requires_one_auth_method(self):
        with pytest.raises(ValueError, match="Either api_token"):
            MtsLinkAPI()
        with pytest.raises(ValueError, match="only one"):
            MtsLinkAPI(api_token="k", access_token="b")

    @pytest.mark.asyncio
    async def test_list_records_parses_array(self):
        client = MtsLinkAPI(api_token="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[{"id": 1}]'
        mock_response.json.return_value = [{"id": 1, "name": "Webinar"}]

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=mock_http):
            rows = await client.list_records(from_date="2025-01-01 00:00:00", limit=1)

        assert len(rows) == 1
        assert rows[0]["id"] == 1
        call_kwargs = mock_http.request.call_args.kwargs
        assert call_kwargs["headers"]["x-auth-token"] == "test-key"
        assert call_kwargs["params"]["from"] == "2025-01-01 00:00:00"

    @pytest.mark.asyncio
    async def test_auth_error_raises(self):
        client = MtsLinkAPI(api_token="bad")
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(MtsLinkAuthenticationError):
                await client.list_records(from_date="2025-01-01 00:00:00")

    @pytest.mark.asyncio
    async def test_network_error_wrapped(self):
        client = MtsLinkAPI(api_token="k")
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(MtsLinkAPIError, match="Network error"):
                await client.list_records(from_date="2025-01-01 00:00:00")

    @pytest.mark.asyncio
    async def test_conversion_busy_403_is_not_auth_error(self):
        """The per-employee conversion limit must stay retryable, not trigger reauth."""
        client = MtsLinkAPI(api_token="k")
        response = _error_response(403, "Simultaneous conversions limit reached")

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=_mock_http(response)):
            with pytest.raises(MtsLinkConversionBusyError) as exc:
                await client.start_conversion(1, quality="720", view="none")

        assert exc.value.status_code == 403
        assert not isinstance(exc.value, MtsLinkAuthenticationError)

    @pytest.mark.asyncio
    async def test_busy_403_recognised_from_running_conversion_id(self):
        """Their busy reply names the running conversion; that beats matching words."""
        client = MtsLinkAPI(api_token="k")
        response = MagicMock()
        response.status_code = 403
        response.text = "Forbidden"
        response.json.return_value = {
            "error": {
                "code": 403,
                "message": "Quantity exceeded",
                "fieldErrors": {"currentConversionID": "6985887", "recordFileId": "6985000"},
            }
        }

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=_mock_http(response)):
            with pytest.raises(MtsLinkConversionBusyError):
                await client.start_conversion(1)

    @pytest.mark.asyncio
    async def test_forbidden_without_conversion_hint_is_auth_error(self):
        client = MtsLinkAPI(api_token="revoked")
        response = _error_response(403, "Access denied")

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=_mock_http(response)):
            with pytest.raises(MtsLinkAuthenticationError):
                await client.list_records(from_date="2025-01-01 00:00:00")

    @pytest.mark.asyncio
    async def test_forbidden_access_to_conversions_is_not_treated_as_busy(self):
        """A dead key must not hide behind the word "conversions" and retry forever."""
        client = MtsLinkAPI(api_token="revoked")
        response = _error_response(403, "No access to conversions for this account")

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=_mock_http(response)):
            with pytest.raises(MtsLinkAuthenticationError):
                await client.start_conversion(1)

    @pytest.mark.asyncio
    async def test_start_conversion_posts_json_body(self):
        client = MtsLinkAPI(api_token="k")
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"id": 55}'
        response.json.return_value = {"id": 55}
        http = _mock_http(response)

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=http):
            result = await client.start_conversion(42, quality="1080", view="none")

        assert result["id"] == 55
        call = http.request.call_args
        assert call.args[0] == "POST"
        assert call.args[1].endswith("/records/42/conversions")
        assert call.kwargs["json"] == {"quality": "1080", "view": "none"}
        assert call.kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_get_ready_mp4_url_returns_none_until_converted(self):
        client = MtsLinkAPI(api_token="k")
        response = MagicMock()
        response.status_code = 200
        response.content = b"[]"
        response.json.return_value = []

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=_mock_http(response)):
            assert await client.get_ready_mp4_url(7) is None


@pytest.mark.unit
class TestMtsLinkPayloadHelpers:
    def test_unwrap_items_handles_wrapped_shapes(self):
        assert unwrap_items([{"id": 1}]) == [{"id": 1}]
        assert unwrap_items({"data": [{"id": 2}]}) == [{"id": 2}]
        assert unwrap_items({"data": {"items": [{"id": 3}]}}) == [{"id": 3}]
        assert unwrap_items({"unexpected": 1}) == []

    def test_extract_download_url_requires_ready_row(self):
        assert extract_download_url({"data": [{"state": "processing"}]}) is None
        assert extract_download_url({"data": [{"downloadUrl": "https://cdn/x.mp4"}]}) == "https://cdn/x.mp4"

    def test_unwrap_conversion_jobs_reads_data_items(self):
        assert unwrap_conversion_jobs({"data": {"items": [{"id": 1}]}}) == [{"id": 1}]
        assert unwrap_conversion_jobs({"items": [{"id": 2}]}) == [{"id": 2}]
        assert unwrap_conversion_jobs("nope") == []

    def test_pick_active_conversion_prefers_furthest_processing(self):
        rows = [
            {"id": 1, "state": "waiting", "progress": 0, "recordFile": {"id": 10}},
            {"id": 2, "state": "processing", "progress": 50, "recordFile": {"id": 10}},
            {"id": 3, "state": "processing", "progress": 81, "recordFile": {"id": 10}},
            {"id": 4, "state": "processing", "progress": 99, "recordFile": {"id": 99}},
            {"id": 5, "state": "completed", "progress": 100, "recordFile": {"id": 10}},
        ]
        picked = pick_active_conversion(rows, 10)
        assert picked is not None
        assert picked["id"] == 3

    def test_pick_active_conversion_empty_when_nothing_in_flight(self):
        assert pick_active_conversion([{"id": 1, "state": "failed", "recordFile": {"id": 10}}], 10) is None
        assert pick_active_conversion([], 10) is None
