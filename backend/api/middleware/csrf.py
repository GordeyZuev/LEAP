"""Apply CSRF check on every request before route dispatch.

Implemented as a pure ASGI middleware (not ``BaseHTTPMiddleware``): the latter
spawns a sub-task that breaks asyncpg's event-loop affinity under TestClient.
"""

from __future__ import annotations

import json

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Receive, Scope, Send

from api.auth.csrf import enforce_csrf


class CSRFMiddleware:
    """ASGI middleware that enforces the double-submit CSRF cookie."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the inner ASGI app."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the CSRF check on HTTP requests; pass other ASGI scopes through."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            enforce_csrf(Request(scope, receive=receive))
        except HTTPException as exc:
            body = json.dumps({"detail": exc.detail}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": exc.status_code,
                    "headers": [(b"content-type", b"application/json")],
                },
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
