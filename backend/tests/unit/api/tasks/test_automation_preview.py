from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.tasks.automation import (
    _execute_job,
    _MatchPlan,
    _preview_job,
    _record_run,
    _would_process_items,
)
from models.recording import ProcessingStatus


@pytest.mark.unit
def test_would_process_items_snapshot():
    rec = SimpleNamespace(id=12, display_name="Lecture 3")
    tmpl = SimpleNamespace(id=3, name="HSE default")
    assert _would_process_items([(rec, tmpl)]) == [
        {"id": 12, "name": "Lecture 3", "template_id": 3, "template_name": "HSE default"},
    ]


@pytest.mark.unit
def test_preview_payload_has_would_process_not_enqueue_fields():
    rec = SimpleNamespace(id=1, display_name="A")
    tmpl = SimpleNamespace(id=2, name="T")
    plan = _MatchPlan(
        templates=[tmpl],
        sources_to_sync=[SimpleNamespace(id=9)],
        synced_count=3,
        recordings_found=5,
        unmatched_count=1,
        matches=[(rec, tmpl)],
        unmatched=[],
    )
    payload = plan.preview_payload(7, "u1")
    assert payload["status"] == "success"
    assert payload["user_id"] == "u1"
    assert payload["synced_count"] == 3
    assert payload["sources_synced"] == [9]
    assert payload["matched_count"] == 1
    assert payload["would_process"][0]["id"] == 1
    assert "processed_recordings" not in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_run_persists_would_process():
    captured: dict = {}

    class Repo:
        def __init__(self, _session):
            pass

        async def create(self, **kwargs):
            captured.update(kwargs)

    snapshot = [{"id": 8, "name": "A", "template_id": 2, "template_name": "T"}]
    with patch("api.tasks.automation.AutomationJobRunRepository", Repo):
        await _record_run(
            MagicMock(),
            4,
            "user_1",
            datetime(2026, 9, 10, tzinfo=UTC),
            {
                "status": "success",
                "synced_count": 1,
                "recordings_found": 2,
                "matched_count": 1,
                "processed_count": 1,
                "would_process": snapshot,
            },
            "MANUAL",
        )
    assert captured["affected_recordings"] == snapshot
    assert captured["trigger"] == "MANUAL"
    assert captured["status"] == "SUCCESS"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_job_commits_after_successful_match():
    session = MagicMock()
    session.commit = AsyncMock()
    rec = SimpleNamespace(id=1, display_name="A")
    tmpl = SimpleNamespace(id=2, name="T")
    plan = _MatchPlan(
        templates=[tmpl],
        sources_to_sync=[SimpleNamespace(id=9)],
        synced_count=3,
        recordings_found=5,
        unmatched_count=1,
        matches=[(rec, tmpl)],
        unmatched=[],
    )
    job = SimpleNamespace(id=7)

    with patch("api.tasks.automation._sync_and_match", new_callable=AsyncMock, return_value=plan):
        payload = await _preview_job(session, job, "u1")

    session.commit.assert_awaited()
    assert payload["would_process"][0]["id"] == 1
    assert payload["job_id"] == 7


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_job_skips_commit_on_match_error():
    session = MagicMock()
    session.commit = AsyncMock()
    job = SimpleNamespace(id=7)

    with patch(
        "api.tasks.automation._sync_and_match",
        new_callable=AsyncMock,
        return_value={"status": "error", "error": "No active templates", "user_id": "u1"},
    ):
        result = await _preview_job(session, job, "u1")

    assert result["status"] == "error"
    session.commit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_inactive_job_skips_without_sync():
    session = MagicMock()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1, is_active=False, name="off"))

    with (
        patch("api.tasks.automation.AutomationJobRepository", return_value=repo),
        patch("api.tasks.automation._sync_and_match", new_callable=AsyncMock) as sync_match,
    ):
        result = await _execute_job(session, 1, "u1")

    assert result["status"] == "skipped"
    sync_match.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_job_enqueues_matched_recordings():
    rec = SimpleNamespace(
        id=9,
        display_name="A",
        is_mapped=True,
        template_id=1,
        status=ProcessingStatus.INITIALIZED,
    )
    tmpl = SimpleNamespace(id=1, name="T")
    plan = _MatchPlan(
        templates=[tmpl],
        sources_to_sync=[SimpleNamespace(id=4)],
        synced_count=2,
        recordings_found=1,
        unmatched_count=0,
        matches=[(rec, tmpl)],
        unmatched=[],
    )
    job = SimpleNamespace(
        id=5,
        name="daily",
        is_active=True,
        processing_config=None,
        schedule={"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"},
    )
    session = MagicMock()
    session.commit = AsyncMock()
    job_repo = MagicMock()
    job_repo.get_by_id = AsyncMock(return_value=job)
    job_repo.mark_run = AsyncMock()
    tmpl_repo = MagicMock()
    tmpl_repo.increment_usage = AsyncMock()
    delay = MagicMock(return_value=SimpleNamespace(id="task-1"))

    with (
        patch("api.tasks.automation.AutomationJobRepository", return_value=job_repo),
        patch("api.tasks.automation.RecordingTemplateRepository", return_value=tmpl_repo),
        patch("api.tasks.automation._sync_and_match", new_callable=AsyncMock, return_value=plan),
        patch("api.tasks.automation.run_recording_task") as run_task,
        patch("api.tasks.automation.schedule_to_cron", return_value=("0 9 * * *", "daily")),
        patch("api.tasks.automation.get_next_run_time", return_value=datetime(2026, 9, 11, tzinfo=UTC)),
    ):
        run_task.delay = delay
        result = await _execute_job(session, 5, "u1")

    delay.assert_called_once()
    assert result["processed_count"] == 1
    assert result["would_process"][0]["id"] == 9
    assert result["processed_recordings"][0]["task_id"] == "task-1"
    job_repo.mark_run.assert_awaited()
    tmpl_repo.increment_usage.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_job_marks_unmatched_skipped():
    rec = SimpleNamespace(
        id=3,
        display_name="B",
        status=ProcessingStatus.INITIALIZED,
        failed_reason=None,
    )
    plan = _MatchPlan(
        templates=[],
        sources_to_sync=[SimpleNamespace(id=1)],
        synced_count=0,
        recordings_found=1,
        unmatched_count=1,
        matches=[],
        unmatched=[rec],
    )
    job = SimpleNamespace(
        id=5,
        name="daily",
        is_active=True,
        processing_config=None,
        schedule={"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"},
    )
    session = MagicMock()
    session.commit = AsyncMock()
    job_repo = MagicMock()
    job_repo.get_by_id = AsyncMock(return_value=job)
    job_repo.mark_run = AsyncMock()

    with (
        patch("api.tasks.automation.AutomationJobRepository", return_value=job_repo),
        patch("api.tasks.automation.RecordingTemplateRepository", return_value=MagicMock()),
        patch("api.tasks.automation._sync_and_match", new_callable=AsyncMock, return_value=plan),
        patch("api.tasks.automation.run_recording_task") as run_task,
        patch("api.tasks.automation.schedule_to_cron", return_value=("0 9 * * *", "daily")),
        patch("api.tasks.automation.get_next_run_time", return_value=datetime(2026, 9, 11, tzinfo=UTC)),
    ):
        run_task.delay = MagicMock()
        await _execute_job(session, 5, "u1")

    assert rec.status == ProcessingStatus.SKIPPED
    assert rec.failed_reason == "No matching template"
    run_task.delay.assert_not_called()
