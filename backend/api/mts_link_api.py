"""MTS Link UserAPI client (org API key or OAuth Bearer — auth supplied by caller)."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from logger import get_logger

logger = get_logger()

DEFAULT_BASE_URL = "https://userapi.mts-link.ru/v3"


class MtsLinkAPIError(Exception):
    """Base MTS Link API error."""


class MtsLinkAuthenticationError(MtsLinkAPIError):
    """Invalid or missing API credentials."""


class MtsLinkResponseError(MtsLinkAPIError):
    """Non-success HTTP response from UserAPI."""

    def __init__(self, status_code: int, message: str, *, payload: Any | None = None):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"MTS Link API error {status_code}: {message}")


class MtsLinkConversionBusyError(MtsLinkResponseError):
    """UserAPI refused a conversion because another one is already running.

    MTS Link answers 403 for both revoked keys and the "one conversion at a time"
    limit; this subclass keeps the latter retryable instead of triggering reauth.
    """


# UserAPI answers 403 both for a dead key and for the "one conversion per employee"
# limit. The busy reply names the conversion already running, which is a far more
# precise signal than matching words in the message.
_CONVERSION_BUSY_FIELD = "currentConversionID"
_CONVERSION_BUSY_MARKER = "simultaneous"


def _is_conversion_busy(message: str, payload: Any) -> bool:
    """True when a 403 means a conversion is already running, not that the key is dead."""
    if isinstance(payload, dict):
        error = payload.get("error")
        field_errors = error.get("fieldErrors") if isinstance(error, dict) else None
        if isinstance(field_errors, dict) and _CONVERSION_BUSY_FIELD in field_errors:
            return True
    return _CONVERSION_BUSY_MARKER in message.lower()


def unwrap_items(payload: Any) -> list[Any]:
    """Normalize UserAPI collection payloads, which are a bare list or wrapped in ``data``."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict) and isinstance(inner.get("items"), list):
                return inner["items"]
    return []


def extract_download_url(converted_payload: Any) -> str | None:
    """First finished MP4 URL in a converted-records payload, or None if none is ready.

    A row only carries ``downloadUrl`` once its conversion finished, so presence of
    the field is the readiness signal.
    """
    for item in unwrap_items(converted_payload):
        if isinstance(item, dict) and item.get("downloadUrl"):
            return str(item["downloadUrl"])
    return None


_IN_FLIGHT_CONVERSION_STATES = frozenset({"waiting", "processing", "loaded"})


def unwrap_conversion_jobs(payload: Any) -> list[dict[str, Any]]:
    """Rows from ``GET /converted-records`` (``data.items`` or a bare list)."""
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data["items"]
        elif isinstance(payload.get("items"), list):
            items = payload["items"]
        else:
            items = unwrap_items(payload)
    else:
        items = unwrap_items(payload)
    return [item for item in items if isinstance(item, dict)]


def conversion_record_file_id(row: dict[str, Any]) -> Any:
    """Online-record id a conversion job belongs to, if the row names one."""
    record_file = row.get("recordFile")
    if isinstance(record_file, dict) and record_file.get("id") is not None:
        return record_file["id"]
    return row.get("recordFileId") or row.get("recordFileID")


def pick_active_conversion(rows: list[dict[str, Any]], record_id: int | str) -> dict[str, Any] | None:
    """In-flight job for this online record, preferring the furthest along.

    ``GET /eventsessions/.../converted-records`` only lists finished MP4s. Jobs still
    rendering show up on ``GET /converted-records`` instead; we wait on those rather
    than queueing another render of the same file.
    """
    want = str(record_id)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if str(conversion_record_file_id(row) or "") != want:
            continue
        state = str(row.get("state") or "").lower()
        if state in _IN_FLIGHT_CONVERSION_STATES:
            candidates.append(row)
    if not candidates:
        return None

    def _rank(row: dict[str, Any]) -> tuple[int, int]:
        state = str(row.get("state") or "").lower()
        try:
            progress = int(row.get("progress") or 0)
        except (TypeError, ValueError):
            progress = 0
        # processing first, then waiting/loaded; higher progress wins
        return (0 if state == "processing" else 1, -progress)

    candidates.sort(key=_rank)
    return candidates[0]


class MtsLinkAPI:
    """Thin async client for MTS Link UserAPI v3."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        access_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
    ):
        if not api_token and not access_token:
            raise ValueError("Either api_token (x-auth-token) or access_token (Bearer) is required")
        if api_token and access_token:
            raise ValueError("Provide only one of api_token or access_token")

        self._api_token = api_token
        self._access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _auth_headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {"Content-Type": "application/json" if json_body else "application/x-www-form-urlencoded"}
        if self._api_token:
            headers["x-auth-token"] = self._api_token
        else:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    @staticmethod
    def _extract_error(response: httpx.Response) -> tuple[str, Any]:
        """Best-effort error message + parsed payload from a failed response."""
        message = response.text[:500]
        try:
            payload: Any = response.json()
        except ValueError:
            return message, None

        if isinstance(payload, dict):
            err = payload.get("error") or payload
            message = str(err.get("message") if isinstance(err, dict) else err) or message
        return message, payload

    async def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._auth_headers(json_body=json_body is not None),
                    params=params,
                    json=json_body,
                )
        except httpx.RequestError as e:
            raise MtsLinkAPIError(f"Network error: {e}") from e

        if response.status_code >= 400:
            message, payload = self._extract_error(response)

            if response.status_code == 401:
                raise MtsLinkAuthenticationError(f"Authentication failed (401): {message}")

            if response.status_code == 403:
                if _is_conversion_busy(message, payload):
                    raise MtsLinkConversionBusyError(403, message, payload=payload)
                raise MtsLinkAuthenticationError(f"Authentication failed (403): {message}")

            raise MtsLinkResponseError(response.status_code, message, payload=payload)

        if not response.content:
            return None
        try:
            return response.json()
        except Exception as e:
            raise MtsLinkResponseError(response.status_code, f"Invalid JSON: {response.text[:200]}") from e

    async def list_records(
        self,
        *,
        from_date: str,
        to_date: str | None = None,
        offset: int = 0,
        limit: int = 10,
        user_id: int | None = None,
        record_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """GET /records — online webinar recordings for a date range."""
        params: dict[str, str | int] = {
            "from": from_date,
            "offset": offset,
            "limit": limit,
        }
        if to_date:
            params["to"] = to_date
        if user_id is not None:
            params["userId"] = user_id
        if record_id is not None:
            params["id"] = record_id

        data = await self._request("GET", "records", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, list):
                return inner
        raise MtsLinkResponseError(200, "Unexpected list_records response shape", payload=data)

    async def list_organization_members(
        self,
        *,
        email: str | None = None,
        user_id: int | None = None,
        role: str | None = None,
        page: int = 1,
        per_page: int | None = None,
    ) -> list[dict[str, Any]]:
        """GET /organization/members — employees with id, email, name, role.

        ``role`` filter values in API docs: ``admin``, ``lecturer`` (case per API).
        ``per_page`` allowed: 10, 50, 100, 250, 500; omit for all members (API default).
        """
        params: dict[str, str | int] = {"page": page}
        if per_page is not None:
            allowed = (10, 50, 100, 250, 500)
            if per_page not in allowed:
                raise ValueError(f"per_page must be one of {allowed}, got {per_page}")
            params["perPage"] = per_page
        if email:
            params["email"] = email
        if user_id is not None:
            params["id"] = user_id
        if role:
            params["role"] = role

        data = await self._request("GET", "organization/members", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, list):
                return inner
        raise MtsLinkResponseError(200, "Unexpected organization/members response shape", payload=data)

    async def start_conversion(
        self, record_id: int | str, *, quality: str = "720", view: str = "none"
    ) -> dict[str, Any]:
        """POST /records/{recordId}/conversions — order an MP4 render of an online recording.

        ``view`` picks what gets baked into the frame (``none`` keeps presenter video
        only). Raises :class:`MtsLinkConversionBusyError` while another conversion
        for the same employee is still running.
        """
        data = await self._request(
            "POST",
            f"records/{record_id}/conversions",
            json_body={"quality": quality, "view": view},
        )
        if isinstance(data, dict):
            return data
        raise MtsLinkResponseError(200, "Unexpected start_conversion response", payload=data)

    async def get_conversion_status(self, conversion_id: int | str) -> dict[str, Any]:
        """GET /records/conversions/{conversionId}."""
        data = await self._request("GET", f"records/conversions/{conversion_id}")
        if isinstance(data, dict):
            return data
        raise MtsLinkResponseError(200, "Unexpected conversion status response", payload=data)

    async def get_converted_records_by_event_session(self, event_session_id: int | str) -> Any:
        """GET /eventsessions/{eventSessionId}/converted-records."""
        return await self._request("GET", f"eventsessions/{event_session_id}/converted-records")

    async def get_event_session_chat(self, event_session_id: int | str) -> Any:
        """GET /eventsessions/{eventSessionId}/chat — raw chat log payload."""
        return await self._request("GET", f"eventsessions/{event_session_id}/chat")

    async def list_event_session_files(self, event_session_id: int | str) -> list[dict[str, Any]]:
        """GET /eventsessions/{eventSessionId}/files — presentations, PDFs and other attachments."""
        payload = await self._request("GET", f"eventsessions/{event_session_id}/files")
        return [item for item in unwrap_items(payload) if isinstance(item, dict)]

    async def get_ready_mp4_url(self, event_session_id: int | str) -> str | None:
        """Download URL of an already converted MP4, or None if no conversion finished.

        Always re-read before streaming: CDN links in stored metadata go stale.
        """
        payload = await self.get_converted_records_by_event_session(event_session_id)
        return extract_download_url(payload)

    async def list_converted_records(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> dict[str, Any]:
        """GET /converted-records — MP4 conversion jobs.

        ``from``/``to`` must be ``yyyy-mm-dd`` (date only). ``perPage`` allowed: 10, 25, 50, 100, 250, 500.
        """
        allowed_per_page = (10, 25, 50, 100, 250, 500)
        if per_page not in allowed_per_page:
            raise ValueError(f"per_page must be one of {allowed_per_page}, got {per_page}")

        params: dict[str, str | int] = {"page": page, "perPage": per_page}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        data = await self._request("GET", "converted-records", params=params)
        if isinstance(data, dict):
            return data
        raise MtsLinkResponseError(200, "Unexpected converted-records response", payload=data)
