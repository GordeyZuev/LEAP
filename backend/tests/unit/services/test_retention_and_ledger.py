"""Retention deadlines and ledger rows that must not become processing minutes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.celery_app import disable_retired_beat_tasks
from api.repositories.recording_repos import RecordingRepository
from api.services.analytics_service import _LEDGER_MINUTES_BY_DAY
from api.services.resource_ledger import (
    RecordingAttemptHooks,
    ResourceLedgerService,
    recording_id_from_audio_url,
    resume_transcript_id,
    should_import_untracked,
    transcript_after_backfill,
)
from api.services.retention import (
    apply_retention_deadline,
    effective_retention_exempt,
    hard_delete_deadline,
    retention_exempt_from_layers,
    still_due_for_hard_delete,
)
from database.automation_models import AutomationJobModel
from database.config_models import UserConfigModel

# Importing these registers relationships on UserModel before a ledger row is constructed.
_REGISTERED_MODELS = (AutomationJobModel, UserConfigModel)


def _recording(**overrides):
    fields = {
        "id": 7,
        "user_id": "user",
        "deleted": False,
        "delete_state": "active",
        "deletion_reason": None,
        "retention_exempt": False,
        "pipeline_task_id": None,
        "on_air": False,
        "expire_at": None,
        "deleted_at": None,
        "soft_deleted_at": None,
        "hard_delete_at": None,
        "updated_at": None,
        "owner": None,
        "local_video_path": None,
        "processed_video_path": None,
        "processed_audio_path": None,
        "transcription_dir": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.mark.unit
def test_provider_import_does_not_repeat_historical_estimates():
    cutoff = datetime(2026, 10, 1, tzinfo=UTC)
    assert transcript_after_backfill(datetime(2026, 10, 2, tzinfo=UTC), cutoff) is True
    assert transcript_after_backfill(cutoff, cutoff) is False
    assert transcript_after_backfill(datetime(2026, 9, 1, tzinfo=UTC), None) is True
    url = "https://storage.example/users/user_000003/recordings/7/audio.mp3?X-Amz-Signature=abc"
    assert recording_id_from_audio_url(url) == 7
    assert recording_id_from_audio_url("https://cdn.example/upload/abc") is None
    older = datetime(2026, 9, 1, tzinfo=UTC)
    newer = datetime(2026, 10, 2, tzinfo=UTC)
    assert should_import_untracked(
        created=older, watermark=cutoff, recording_id=7, pending_match=False, estimate_at=None
    )
    assert not should_import_untracked(
        created=older, watermark=cutoff, recording_id=7, pending_match=False, estimate_at=cutoff
    )
    assert should_import_untracked(
        created=newer, watermark=cutoff, recording_id=7, pending_match=False, estimate_at=cutoff
    )
    assert should_import_untracked(
        created=older, watermark=cutoff, recording_id=None, pending_match=True, estimate_at=cutoff
    )
    assert not should_import_untracked(
        created=older, watermark=cutoff, recording_id=None, pending_match=False, estimate_at=None
    )


@pytest.mark.unit
def test_resume_polls_a_completed_job_from_the_same_attempt():
    assert resume_transcript_id("open-job", "older-job", "completed") == "open-job"
    assert resume_transcript_id(None, "job", "completed") == "job"
    assert resume_transcript_id(None, "job", None) == "job"
    assert resume_transcript_id(None, "job", "failed") is None
    assert resume_transcript_id(None, None, None) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attempt_hook_stamps_job_before_ledger_write():
    session = AsyncMock()
    timing = SimpleNamespace(meta={"language": "ru"})
    inner = AsyncMock()
    inner.submitted = AsyncMock(side_effect=RuntimeError("ledger down"))
    hooks = RecordingAttemptHooks(inner=inner, session=session, timing=timing, celery_task_id="task-1")

    with pytest.raises(RuntimeError, match="ledger down"):
        await hooks.submitted("job-9")

    assert timing.meta["provider_job_id"] == "job-9"
    assert timing.meta["celery_task_id"] == "task-1"
    assert timing.meta["language"] == "ru"
    session.commit.assert_awaited_once()


@pytest.mark.unit
def test_retired_file_cleanup_beat_row_is_disabled():
    row = SimpleNamespace(name="cleanup-recording-files", task="maintenance.cleanup_recording_files", enabled=True)
    kept = SimpleNamespace(name="auto-expire-recordings", task="maintenance.auto_expire_recordings", enabled=True)
    session = MagicMock()
    session.query.return_value.all.return_value = [row, kept]
    schedule = {
        "cleanup-recording-files": SimpleNamespace(task="maintenance.cleanup_recording_files"),
        "auto-expire-recordings": SimpleNamespace(task="maintenance.auto_expire_recordings"),
    }
    scheduler = SimpleNamespace(session=session, schedule=schedule)
    names = disable_retired_beat_tasks(scheduler)

    assert names == ["cleanup-recording-files"]
    assert row.enabled is False
    assert kept.enabled is True
    assert "cleanup-recording-files" not in schedule
    assert "auto-expire-recordings" in schedule
    session.commit.assert_called_once()


@pytest.mark.unit
def test_hard_delete_at_is_deleted_at_plus_hard_days():
    deleted_at = datetime(2026, 1, 1, tzinfo=UTC)
    assert hard_delete_deadline(deleted_at, 30) == deleted_at + timedelta(days=30)


@pytest.mark.unit
def test_restore_during_hard_delete_list_is_not_due():
    restored = _recording(delete_state="active", deleted=False, hard_delete_at=None)
    assert still_due_for_hard_delete(restored, datetime.now(UTC)) is False


@pytest.mark.unit
def test_legacy_hard_state_stays_due():
    past = datetime.now(UTC) - timedelta(hours=1)
    legacy = _recording(delete_state="hard", deleted=True, hard_delete_at=past)
    assert still_due_for_hard_delete(legacy, datetime.now(UTC)) is True


@pytest.mark.unit
def test_processing_minutes_ignore_deepseek_and_failures():
    assert "assemblyai" in _LEDGER_MINUTES_BY_DAY
    assert "status = 'completed'" in _LEDGER_MINUTES_BY_DAY
    assert "deepseek" not in _LEDGER_MINUTES_BY_DAY
    assert "failed" not in _LEDGER_MINUTES_BY_DAY


@pytest.mark.unit
@pytest.mark.asyncio
async def test_topic_usage_does_not_set_audio_seconds():
    session = AsyncMock()
    session.add = MagicMock()
    await ResourceLedgerService(session).record_topic_usage(
        user_id="user",
        recording_id=7,
        model="deepseek-flash",
        usage={"prompt_tokens": 11, "completion_tokens": 4},
    )
    row = session.add.call_args[0][0]
    assert row.provider == "deepseek"
    assert row.audio_seconds is None
    assert row.prompt_tokens == 11
    assert row.completion_tokens == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_soft_delete_hides_exempt_recording_and_sets_deadline():
    session = AsyncMock()
    recording = _recording(retention_exempt=True, pipeline_task_id="task-1", on_air=True)
    with patch("api.celery_app.celery_app") as celery:
        await RecordingRepository(session).soft_delete(recording, {"retention": {"hard_delete_days": 12}})
    celery.control.revoke.assert_called_once()
    assert recording.deleted is True
    assert recording.delete_state == "soft"
    assert recording.hard_delete_at - recording.deleted_at == timedelta(days=12)
    assert recording.pipeline_task_id is None


@pytest.mark.unit
def test_retention_override_wins_over_the_template():
    assert effective_retention_exempt(None, True) is True
    assert effective_retention_exempt(None, False) is False
    assert effective_retention_exempt(True, False) is True
    assert effective_retention_exempt(False, True) is False
    assert (
        retention_exempt_from_layers(
            {"transcription": {"retention_exempt": True}},
            {"transcription": {"retention_exempt": False}},
        )
        is False
    )
    assert retention_exempt_from_layers({"transcription": {"language": "ru"}}) is False


@pytest.mark.unit
def test_turning_protection_off_keeps_an_existing_auto_hide_date():
    existing = datetime(2027, 1, 3, tzinfo=UTC)
    recording = _recording(retention_exempt=None, expire_at=existing)
    apply_retention_deadline(recording, False, {"retention": {"auto_expire_days": 10}}, datetime.now(UTC))
    assert recording.expire_at == existing
    protected = _recording(retention_exempt=None, expire_at=existing)
    apply_retention_deadline(protected, True, {"retention": {"auto_expire_days": 10}}, datetime.now(UTC))
    assert protected.expire_at is None
    missing = _recording(retention_exempt=False, expire_at=None)
    moment = datetime(2026, 10, 5, tzinfo=UTC)
    apply_retention_deadline(missing, True, {"retention": {"auto_expire_days": 10}}, moment)
    assert missing.expire_at == moment + timedelta(days=10)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auto_expire_skips_a_recording_the_template_keeps():
    session = AsyncMock()
    recording = _recording(retention_exempt=None)
    await RecordingRepository(session).auto_expire(recording, {"retention": {}}, template_exempt=True)
    assert recording.deleted is False
    session.flush.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auto_expire_skips_exempt_recording():
    session = AsyncMock()
    recording = _recording(retention_exempt=True)
    await RecordingRepository(session).auto_expire(recording, {"retention": {"hard_delete_days": 12}})
    assert recording.deleted is False
    session.flush.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hard_delete_lists_recording_prefix():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    recording = _recording(owner=SimpleNamespace(user_slug=3))
    storage = AsyncMock()
    storage.list_keys = AsyncMock(return_value=["users/user_000003/recordings/7/poster.jpg"])
    storage.delete = AsyncMock(return_value=True)
    storage.exists = AsyncMock(return_value=False)
    with patch("file_storage.factory.get_storage_backend", return_value=storage):
        await RecordingRepository(session).delete(recording)
    prefix = storage.list_keys.await_args.args[0]
    assert prefix == "users/user_000003/recordings/7/"
    storage.delete.assert_awaited()
    session.delete.assert_awaited_once_with(recording)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wipe_keeps_keys_that_failed_to_delete():
    session = AsyncMock()
    recording = _recording(
        owner=SimpleNamespace(user_slug=3),
        processed_audio_path="users/user_000003/stray.mp3",
        transcription_dir="users/user_000003/recordings/7/transcription",
    )
    storage = AsyncMock()
    storage.list_keys = AsyncMock(side_effect=RuntimeError("list down"))
    storage.exists = AsyncMock(return_value=True)
    storage.delete = AsyncMock(side_effect=RuntimeError("delete down"))
    with patch("file_storage.factory.get_storage_backend", return_value=storage):
        _deleted, errors = await RecordingRepository(session).wipe_recording_storage(recording)
    assert errors
    assert recording.processed_audio_path == "users/user_000003/stray.mp3"
    assert recording.transcription_dir == "users/user_000003/recordings/7/transcription"
