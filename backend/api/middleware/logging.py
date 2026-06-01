"""HTTP access logging middleware — one structured INFO event per request."""

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from logger import get_logger

logger = get_logger("http.access")

# High-frequency polling endpoints — skipping keeps Loki signal-to-noise high.
_SKIP_PATHS: frozenset[str] = frozenset({"/api/v1/health", "/metrics"})


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self._header = header_name

    async def dispatch(self, request: Request, call_next):
        # Honor an inbound request id (nginx / LB) so traces span edge → backend.
        request_id = request.headers.get(self._header) or uuid.uuid4().hex
        request.state.request_id = request_id

        path = request.url.path
        method = request.method
        skip = path in _SKIP_PATHS

        with logger.contextualize(request_id=request_id, method=method, path=path):
            start = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                if not skip:
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.bind(
                        status_code=500,
                        duration_ms=round(duration_ms, 2),
                        user_id=getattr(request.state, "user_id", None),
                        client_ip=_client_ip(request),
                    ).exception("HTTP {} {} → 500 unhandled", method, path)
                raise

            duration_ms = (time.perf_counter() - start) * 1000
            response.headers[self._header] = request_id

            if skip:
                return response

            # Route TEMPLATE (``/api/v1/recordings/{id}``) — bounded cardinality
            # for Prometheus/Loki aggregations vs the raw path.
            route = _route_template(request) or path

            logger.bind(
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                route=route,
                user_id=getattr(request.state, "user_id", None),
                client_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                bytes_sent=_content_length(response),
            ).log(
                _level_for_status(response.status_code),
                "HTTP {} {} → {} in {:.1f}ms",
                method,
                route,
                response.status_code,
                duration_ms,
            )

            return response


def _route_template(request: Request) -> str | None:
    route = request.scope.get("route")
    return getattr(route, "path", None) if route is not None else None


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _content_length(response) -> int | None:
    value = response.headers.get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _level_for_status(status_code: int) -> str:
    if status_code >= 500:
        return "ERROR"
    if status_code >= 400:
        return "WARNING"
    return "INFO"
