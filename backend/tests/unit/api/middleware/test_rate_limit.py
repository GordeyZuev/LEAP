"""Rate-limit middleware: client IP behind a proxy, auth vs hourly, health skip."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.middleware import rate_limit as rl
from api.middleware.rate_limit import RateLimitMiddleware, client_ip_for_rate_limit


def _request(*, client_host: str | None, headers: dict[str, str] | None = None) -> Request:
    encoded = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": encoded,
        "client": (client_host, 12345) if client_host else None,
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope)


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, _key: str, _ttl: int) -> bool:
        return True


def _app(monkeypatch, *, hour_limit: int = 1000, minute_limit: int = 60, auth_limit: int = 10):
    monkeypatch.setattr(rl.settings.security, "rate_limit_enabled", True)
    monkeypatch.setattr(rl.settings.security, "rate_limit_per_minute", minute_limit)
    monkeypatch.setattr(rl.settings.security, "rate_limit_per_hour", hour_limit)
    monkeypatch.setattr(rl.settings.security, "rate_limit_auth_per_minute", auth_limit)
    monkeypatch.setattr(rl.settings.security, "trust_x_forwarded_for", False)
    fake = _FakeRedis()

    async def _get_redis():
        return fake

    monkeypatch.setattr(rl, "get_redis", _get_redis)

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/users/me")
    def me():
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    def login():
        return {"ok": True}

    @app.get("/metrics")
    def metrics():
        return {"ok": True}

    @app.get("/api/v1/health/live")
    def live():
        return {"ok": True}

    return app, fake


@pytest.mark.unit
def test_private_peer_uses_x_real_ip(monkeypatch):
    monkeypatch.setattr(rl.settings.security, "trust_x_forwarded_for", False)
    req = _request(
        client_host="172.18.0.4",
        headers={"x-real-ip": "203.0.113.10", "x-forwarded-for": "198.51.100.7"},
    )
    assert client_ip_for_rate_limit(req) == "203.0.113.10"


@pytest.mark.unit
def test_private_peer_falls_back_to_x_forwarded_for(monkeypatch):
    monkeypatch.setattr(rl.settings.security, "trust_x_forwarded_for", False)
    req = _request(client_host="172.18.0.4", headers={"x-forwarded-for": "198.51.100.7, 172.18.0.4"})
    assert client_ip_for_rate_limit(req) == "198.51.100.7"


@pytest.mark.unit
def test_public_peer_ignores_spoofed_headers_unless_flag(monkeypatch):
    monkeypatch.setattr(rl.settings.security, "trust_x_forwarded_for", False)
    req = _request(client_host="8.8.8.8", headers={"x-real-ip": "203.0.113.10"})
    assert client_ip_for_rate_limit(req) == "8.8.8.8"

    monkeypatch.setattr(rl.settings.security, "trust_x_forwarded_for", True)
    assert client_ip_for_rate_limit(req) == "203.0.113.10"


@pytest.mark.unit
def test_hourly_limit_returns_429(monkeypatch):
    app, _fake = _app(monkeypatch, hour_limit=1)
    with TestClient(app) as client:
        assert client.get("/api/v1/users/me").status_code == 200
        blocked = client.get("/api/v1/users/me")
        assert blocked.status_code == 429
        assert blocked.json()["retry_after"] == 3600


@pytest.mark.unit
def test_auth_login_not_blocked_by_global_hourly(monkeypatch):
    app, _fake = _app(monkeypatch, hour_limit=1)
    with TestClient(app) as client:
        assert client.get("/api/v1/users/me").status_code == 200
        assert client.get("/api/v1/users/me").status_code == 429
        login = client.post("/api/v1/auth/login")
        assert login.status_code == 200


@pytest.mark.unit
def test_health_and_metrics_are_exempt(monkeypatch):
    app, fake = _app(monkeypatch, hour_limit=1)
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.get("/metrics").status_code == 200
        assert client.get("/metrics").status_code == 200
        assert fake.counts == {}
