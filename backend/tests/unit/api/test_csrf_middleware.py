"""CSRF middleware behaviour (cookie double-submit pattern).

Tests the middleware against a minimal FastAPI app so we don't depend on the
real route layer's DB / dependency wiring.
"""

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from api.middleware.csrf import CSRFMiddleware


@pytest.fixture
def csrf_client():
    """Tiny app with CSRF middleware, a probe route, and public share beacons."""
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/probe")
    def get_probe():
        return {"ok": True}

    @app.post("/probe")
    def post_probe():
        return {"ok": True}

    @app.delete("/probe")
    def delete_probe():
        return {"ok": True}

    @app.post("/api/v1/share/{token}/beacon")
    def share_beacon(token: str):
        return Response(status_code=204)

    @app.post("/api/v1/share/p/{token}/items/{item_id}/beacon")
    def playlist_beacon(token: str, item_id: int):
        return Response(status_code=204)

    @app.post("/api/v1/recordings/{recording_id}/share/rotate")
    def recording_share_rotate(recording_id: int):
        return {"ok": True}

    with TestClient(app) as c:
        yield c


@pytest.mark.unit
class TestCSRFMiddleware:
    """Double-submit cookie enforcement."""

    def test_safe_methods_pass_without_csrf(self, csrf_client):
        r = csrf_client.get("/probe")
        assert r.status_code == 200

    def test_post_without_session_cookies_passes(self, csrf_client):
        """No auth cookie → user can't be in a cookie session, so CSRF doesn't
        apply (the auth layer will produce its own 401 if the route is
        protected)."""
        r = csrf_client.post("/probe")
        assert r.status_code == 200

    def test_post_with_access_cookie_but_no_csrf_is_rejected(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/probe")
        assert r.status_code == 403
        assert r.json()["detail"] == "CSRF token missing or invalid"

    def test_post_with_refresh_cookie_but_no_csrf_is_rejected(self, csrf_client):
        """Same protection applies to /auth/refresh — only the refresh cookie
        is set there but CSRF must still match."""
        csrf_client.cookies.set("refresh_token", "dummy")
        r = csrf_client.post("/probe")
        assert r.status_code == 403

    def test_post_with_matching_csrf_passes(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        csrf_client.cookies.set("csrf_token", "secret-token")
        r = csrf_client.post("/probe", headers={"X-CSRF-Token": "secret-token"})
        assert r.status_code == 200

    def test_post_with_mismatched_csrf_is_rejected(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        csrf_client.cookies.set("csrf_token", "cookie-value")
        r = csrf_client.post("/probe", headers={"X-CSRF-Token": "header-value"})
        assert r.status_code == 403

    def test_bearer_auth_bypasses_csrf(self, csrf_client):
        """Bearer-authenticated callers (CLI / server-to-server) don't need a
        CSRF token — the browser never auto-attaches Authorization headers."""
        # Even with an access cookie present, Bearer takes precedence and skips CSRF.
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/probe", headers={"Authorization": "Bearer xxx"})
        assert r.status_code == 200

    def test_delete_with_session_cookie_requires_csrf(self, csrf_client):
        """DELETE is also a state-changing method."""
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.delete("/probe")
        assert r.status_code == 403

    def test_get_with_session_cookie_does_not_need_csrf(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.get("/probe")
        assert r.status_code == 200

    def test_share_beacon_skips_csrf_with_session_cookie(self, csrf_client):
        """sendBeacon cannot send X-CSRF-Token; logged-in viewers still send cookies."""
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/api/v1/share/86bf7e22-18c1-4285-bfef-fa4ca8e1dae4/beacon")
        assert r.status_code == 204

    def test_playlist_item_beacon_skips_csrf_with_session_cookie(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/api/v1/share/p/86bf7e22-18c1-4285-bfef-fa4ca8e1dae4/items/1/beacon")
        assert r.status_code == 204

    def test_share_rotate_still_requires_csrf(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/api/v1/share/86bf7e22-18c1-4285-bfef-fa4ca8e1dae4/rotate")
        assert r.status_code == 403

    def test_non_uuid_share_beacon_does_not_skip_csrf(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/api/v1/share/not-a-uuid/beacon")
        assert r.status_code == 403

    def test_owner_share_rotate_still_requires_csrf(self, csrf_client):
        csrf_client.cookies.set("access_token", "dummy")
        r = csrf_client.post("/api/v1/recordings/1/share/rotate")
        assert r.status_code == 403
