"""A bulk preview backfill keeps CPU work bounded and can be rerun."""

from argparse import Namespace
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from scripts import backfill_recording_previews as backfill


def _candidate(recording_id: int, *, status: str | None = None) -> backfill.Candidate:
    trimmed_at = datetime(2026, 10, 15, tzinfo=UTC)
    return backfill.Candidate(
        recording_id=recording_id,
        user_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        user_slug=7,
        video_path=f"recordings/{recording_id}/video.mp4",
        trimmed_at=trimmed_at,
        stage_status=status,
        stage_video_path=f"recordings/{recording_id}/video.mp4" if status else None,
        stage_trimmed_at=trimmed_at if status else None,
    )


def test_completed_requires_vtt_and_current_source() -> None:
    current = _candidate(1, status="COMPLETED")
    stale = replace(current, stage_video_path="old.mp4")
    assert backfill.completed(current, True)
    assert not backfill.completed(current, False)
    assert not backfill.completed(stale, True)


@pytest.mark.asyncio
async def test_default_scan_never_connects_to_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    async def pages(_batch_size: int, _start_after: int):
        yield [_candidate(1)]

    class Storage:
        async def exists(self, _key: str) -> bool:
            return False

    def unexpected_broker(*_args, **_kwargs):
        raise AssertionError("dry-run must not connect to Redis")

    monkeypatch.setattr(backfill, "candidate_pages", pages)
    monkeypatch.setattr(backfill, "get_storage_backend", Storage)
    monkeypatch.setattr(backfill, "from_url", unexpected_broker)

    args = Namespace(run=False, batch_size=100, start_after=0, limit=0, poll_seconds=5, wait_seconds=4500)
    assert await backfill.main(args) == 0


@pytest.mark.asyncio
async def test_bulk_run_waits_before_queueing_next_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    async def pages(_batch_size: int, _start_after: int):
        yield [_candidate(1, status="COMPLETED"), _candidate(2), _candidate(3)]

    class Storage:
        async def exists(self, key: str) -> bool:
            return "/1/" in key

    class Redis:
        async def aclose(self) -> None:
            events.append("close")

    async def enqueue(_redis, recording_id: int, _user_id: str, *, force: bool) -> bool:
        events.append(f"queue:{recording_id}:{force}")
        return True

    async def wait(candidate, _vtt_key, *, interval: int, timeout: int) -> str:
        events.append(f"wait:{candidate.recording_id}:{interval}:{timeout}")
        return "completed"

    monkeypatch.setattr(backfill, "candidate_pages", pages)
    monkeypatch.setattr(backfill, "get_storage_backend", Storage)
    monkeypatch.setattr(backfill, "from_url", lambda *_args, **_kwargs: Redis())
    monkeypatch.setattr(backfill, "enqueue_video_previews", enqueue)
    monkeypatch.setattr(backfill, "wait_for_preview", wait)

    args = Namespace(run=True, batch_size=100, start_after=0, limit=0, poll_seconds=5, wait_seconds=4500)
    assert await backfill.main(args) == 0
    assert events == ["queue:2:False", "wait:2:5:4500", "queue:3:False", "wait:3:5:4500", "close"]


@pytest.mark.asyncio
async def test_bulk_run_reports_unfinished_recordings(monkeypatch: pytest.MonkeyPatch) -> None:
    async def pages(_batch_size: int, _start_after: int):
        yield [_candidate(4)]

    class Storage:
        async def exists(self, _key: str) -> bool:
            return False

    class Redis:
        async def aclose(self) -> None:
            pass

    async def blocked(_redis, _recording_id: int, _user_id: str, *, force: bool) -> bool:
        return False

    monkeypatch.setattr(backfill, "candidate_pages", pages)
    monkeypatch.setattr(backfill, "get_storage_backend", Storage)
    monkeypatch.setattr(backfill, "from_url", lambda *_args, **_kwargs: Redis())
    monkeypatch.setattr(backfill, "enqueue_video_previews", blocked)

    async def inactive(_candidate: backfill.Candidate) -> bool:
        return False

    monkeypatch.setattr(backfill, "preview_is_active", inactive)

    args = Namespace(run=True, batch_size=100, start_after=0, limit=0, poll_seconds=5, wait_seconds=4500)
    assert await backfill.main(args) == 1


@pytest.mark.asyncio
async def test_existing_job_is_waited_for_before_next_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    async def pages(_batch_size: int, _start_after: int):
        yield [_candidate(4), _candidate(5)]

    class Storage:
        async def exists(self, _key: str) -> bool:
            return False

    class Redis:
        async def aclose(self) -> None:
            pass

    async def enqueue(_redis, recording_id: int, _user_id: str, *, force: bool) -> bool:
        events.append(f"queue:{recording_id}")
        return recording_id == 5

    async def active(_candidate: backfill.Candidate) -> bool:
        return True

    async def wait(candidate, _vtt_key, *, interval: int, timeout: int) -> str:
        events.append(f"wait:{candidate.recording_id}")
        return "completed"

    monkeypatch.setattr(backfill, "candidate_pages", pages)
    monkeypatch.setattr(backfill, "get_storage_backend", Storage)
    monkeypatch.setattr(backfill, "from_url", lambda *_args, **_kwargs: Redis())
    monkeypatch.setattr(backfill, "enqueue_video_previews", enqueue)
    monkeypatch.setattr(backfill, "preview_is_active", active)
    monkeypatch.setattr(backfill, "wait_for_preview", wait)

    args = Namespace(run=True, batch_size=100, start_after=0, limit=0, poll_seconds=5, wait_seconds=4500)
    assert await backfill.main(args) == 0
    assert events == ["queue:4", "wait:4", "queue:5", "wait:5"]
