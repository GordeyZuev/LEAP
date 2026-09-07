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

    @pytest.mark.asyncio
    async def test_get_file_accepts_record_id(self):
        client = MtsLinkAPI(api_token="k")
        response = MagicMock()
        response.status_code = 200
        response.content = b"{}"
        response.json.return_value = {"id": 42, "typeFile": "record", "duration": 39.2, "size": 100}
        http = _mock_http(response)

        with patch("api.mts_link_api.httpx.AsyncClient", return_value=http):
            payload = await client.get_file(42)

        assert payload["duration"] == 39.2
        assert http.request.await_args.args[1].endswith("/fileSystem/file/42")


@pytest.mark.unit
class TestMtsLinkPayloadHelpers:
    def test_unwrap_items_handles_wrapped_shapes(self):
        assert unwrap_items([{"id": 1}]) == [{"id": 1}]
        assert unwrap_items({"data": [{"id": 2}]}) == [{"id": 2}]
        assert unwrap_items({"data": {"items": [{"id": 3}]}}) == [{"id": 3}]
        assert unwrap_items({"unexpected": 1}) == []
        assert unwrap_items({"downloadUrl": "https://cdn/x.mp4"}) == [{"downloadUrl": "https://cdn/x.mp4"}]

    def test_extract_download_url_requires_ready_row(self):
        assert extract_download_url({"data": [{"state": "processing"}]}) is None
        assert extract_download_url({"data": [{"downloadUrl": "https://cdn/x.mp4"}]}) == "https://cdn/x.mp4"
        assert extract_download_url({"downloadUrl": "https://cdn/official.mp4"}) == "https://cdn/official.mp4"
        assert extract_download_url({"downloadUrl": "https://cdn/official.mp4"}, 42) == "https://cdn/official.mp4"
        assert (
            extract_download_url(
                {
                    "data": [
                        {"downloadUrl": "https://cdn/a.mp4"},
                        {"downloadUrl": "https://cdn/b.mp4"},
                    ]
                },
                42,
            )
            is None
        )

    def test_extract_download_url_matches_record_id(self):
        payload = {
            "data": [
                {"downloadUrl": "https://cdn/short.mp4", "recordFile": {"id": 1}},
                {"downloadUrl": "https://cdn/lecture.mp4", "recordFile": {"id": 42}},
            ]
        }
        assert extract_download_url(payload, 42) == "https://cdn/lecture.mp4"
        assert extract_download_url(payload, 99) is None
        assert extract_download_url(payload) == "https://cdn/short.mp4"

    def test_extract_download_url_matches_session_file_id(self):
        """Live GET /eventsessions/{id}/converted-records uses fileId, not recordFile."""
        payload = [
            {
                "id": 9001,
                "fileId": 1001,
                "state": "completed",
                "downloadUrl": "https://cdn/session.mp4",
            }
        ]
        assert extract_download_url(payload, 1001) == "https://cdn/session.mp4"
        assert extract_download_url(payload, 1002) is None

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
        assert picked["id"] == 5

    def test_pick_active_conversion_max_processing_without_completed(self):
        rows = [
            {"id": 1, "state": "waiting", "progress": 0, "recordFile": {"id": 10}},
            {"id": 2, "state": "processing", "progress": 50, "recordFile": {"id": 10}},
            {"id": 3, "state": "processing", "progress": 81, "recordFile": {"id": 10}},
            {"id": 4, "state": "processing", "progress": 99, "recordFile": {"id": 99}},
        ]
        picked = pick_active_conversion(rows, 10)
        assert picked is not None
        assert picked["id"] == 3

    def test_pick_active_conversion_processing_beats_canceled_and_waiting(self):
        picked = pick_active_conversion(
            [
                {"id": 1, "state": "canceled", "progress": 0, "recordFile": {"id": 10}},
                {"id": 2, "state": "waiting", "progress": 0, "recordFile": {"id": 10}},
                {"id": 3, "state": "processing", "progress": 68, "recordFile": {"id": 10}},
            ],
            10,
        )
        assert picked is not None
        assert picked["id"] == 3
        assert picked["progress"] == 68

    def test_pick_active_conversion_ignores_undocumented_stop(self):
        assert pick_active_conversion([{"id": 1, "state": "stop", "recordFile": {"id": 10}}], 10) is None
        assert pick_active_conversion([{"id": 1, "state": "stopped", "recordFile": {"id": 10}}], 10) is None
        assert pick_active_conversion([{"id": 1, "state": "running", "recordFile": {"id": 10}}], 10) is None

    def test_pick_active_conversion_empty_when_nothing_in_flight(self):
        assert pick_active_conversion([{"id": 1, "state": "failed", "recordFile": {"id": 10}}], 10) is None
        assert pick_active_conversion([{"id": 1, "state": "canceled", "recordFile": {"id": 10}}], 10) is None
        assert pick_active_conversion([], 10) is None

    def test_pick_active_conversion_reads_bare_record_file_id(self):
        picked = pick_active_conversion(
            [{"id": 9, "state": "processing", "progress": 68, "recordFile": 10}],
            10,
        )
        assert picked is not None
        assert picked["id"] == 9

    def test_pick_active_conversion_ignores_other_record_and_unlabeled(self):
        assert (
            pick_active_conversion(
                [
                    {"id": 1, "state": "canceled", "progress": 0, "recordFile": {"id": 10}},
                    {"id": 2, "state": "processing", "progress": 68},
                    {"id": 3, "state": "processing", "progress": 99, "recordFile": {"id": 99}},
                ],
                10,
            )
            is None
        )

    def test_pick_active_conversion_reads_status_field(self):
        picked = pick_active_conversion(
            [{"id": 9, "status": "processing", "progress": 12, "recordFile": {"id": 10}}],
            10,
        )
        assert picked is not None
        assert picked["id"] == 9

    def test_pick_active_conversion_reuses_completed_without_repost(self):
        picked = pick_active_conversion(
            [{"id": 1, "state": "completed", "recordFile": {"id": 10}}],
            10,
        )
        assert picked is not None
        assert picked["id"] == 1

    def test_prefer_keeps_further_processing_over_new_job(self):
        from api.mts_link_api import prefer_conversion_job

        picked = prefer_conversion_job(
            {"id": 2, "state": "processing", "progress": 5},
            {"id": 1, "state": "processing", "progress": 65},
        )
        assert picked is not None
        assert picked["id"] == 1
        assert picked["progress"] == 65

    def test_prefer_same_id_keeps_list_progress(self):
        from api.mts_link_api import prefer_conversion_job

        picked = prefer_conversion_job(
            {"id": 11, "state": "processing", "progress": 65, "recordFile": {"id": 1}},
            {"id": 11, "state": "processing"},
        )
        assert picked is not None
        assert picked["id"] == 11
        assert picked["progress"] == 65

    def test_prefer_known_without_progress_over_new_low_progress(self):
        from api.mts_link_api import prefer_conversion_job

        picked = prefer_conversion_job(
            {"id": 22, "state": "processing", "progress": 5, "recordFile": {"id": 1}},
            {"id": 11, "state": "processing"},
        )
        assert picked is not None
        assert picked["id"] == 11

    def test_conversion_busy_fields(self):
        from api.mts_link_api import conversion_busy_fields, unwrap_data_object

        payload = {
            "error": {
                "fieldErrors": {"currentConversionID": "6985887", "recordFileId": "6985000"},
            }
        }
        assert conversion_busy_fields(payload) == ("6985887", "6985000")
        assert unwrap_data_object({"data": {"id": 55, "state": "waiting"}})["id"] == 55
