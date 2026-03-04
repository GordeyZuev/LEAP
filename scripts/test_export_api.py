#!/usr/bin/env -S uv run python
"""
Test script for POST /api/v1/recordings/export endpoint.

Run: PYTHONPATH=$PWD uv run python scripts/test_export_api.py
     (or: make test  for full pytest suite)

Uses FastAPI TestClient (mocked auth) - no server required.

---
Example requests (require auth - get token from POST /api/v1/auth/login):

# 1. JSON export by recording IDs (short verbosity)
curl -X POST http://localhost:8000/api/v1/recordings/export \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"recording_ids": [1, 2, 3], "format": "json", "verbosity": "short"}'

# 2. CSV export with filters
curl -X POST http://localhost:8000/api/v1/recordings/export \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filters": {"template_id": 5, "status": ["READY"], "from_date": "2025-01-01", "to_date": "2025-12-31"}, "limit": 500, "format": "csv", "verbosity": "long"}'

# 3. XLSX export (saves to file)
curl -X POST http://localhost:8000/api/v1/recordings/export \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"recording_ids": [1, 2], "format": "xlsx"}' \
  -o recordings_export.xlsx
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.core.dependencies import get_service_context
from api.dependencies import get_db_session
from api.main import app
from models.recording import ProcessingStatus, TargetStatus, TargetType
from tests.fixtures.factories import (
    create_mock_output_target,
    create_mock_recording,
    create_mock_template,
)


def _setup_client():
    """Create TestClient with mocked dependencies."""
    mock_user = MagicMock()
    mock_user.id = "user_123"
    mock_user.email = "test@example.com"
    mock_user.is_active = True

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    def _get_db():
        return mock_session

    def _get_ctx():
        from api.core.context import ServiceContext

        return ServiceContext(session=mock_session, user_id=mock_user.id)

    from api.auth.dependencies import get_current_active_user, get_current_user

    app.dependency_overrides[get_db_session] = _get_db
    app.dependency_overrides[get_service_context] = _get_ctx
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    return TestClient(app)


def main():
    print("Testing POST /api/v1/recordings/export...")
    client = _setup_client()

    mock_template = create_mock_template(template_id=5, name="ML Course")
    youtube_out = create_mock_output_target(
        target_type=TargetType.YOUTUBE,
        status=TargetStatus.UPLOADED,
        target_meta={"video_url": "https://youtube.com/watch?v=test"},
    )
    mock_rec = create_mock_recording(
        record_id=1,
        display_name="Lecture 1 — ML",
        user_id="user_123",
        status=ProcessingStatus.READY,
        template=mock_template,
        main_topics=["ML", "Neural Networks"],
        outputs=[youtube_out],
    )

    mock_repo_instance = MagicMock()
    mock_repo_instance.get_by_ids = AsyncMock(return_value={1: mock_rec})
    mock_repo_class = MagicMock(return_value=mock_repo_instance)

    with patch("api.routers.recordings.RecordingRepository", mock_repo_class):
        # 1. JSON export
        r = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [1],
                "format": "json",
                "verbosity": "short",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["youtube_url"] == "https://youtube.com/watch?v=test"
        print("  ✓ JSON export OK")

        # 2. CSV export
        r = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [1],
                "format": "csv",
                "verbosity": "long",
            },
        )
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers["content-type"]
        print("  ✓ CSV export OK")

        # 3. XLSX export
        r = client.post(
            "/api/v1/recordings/export",
            json={
                "recording_ids": [1],
                "format": "xlsx",
                "verbosity": "short",
            },
        )
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"PK\x03\x04"
        print("  ✓ XLSX export OK")

        # 4. Validation: no ids nor filters
        r = client.post("/api/v1/recordings/export", json={"format": "json"})
        assert r.status_code == 422
        print("  ✓ Validation OK")

    app.dependency_overrides.clear()
    print("\nAll export API checks passed.")


if __name__ == "__main__":
    main()
