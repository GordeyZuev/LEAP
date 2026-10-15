"""Preview cues and public access contract for the embedded player."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.services.video_previews import (
    claim_preview_queue_lock,
    enqueue_poster,
    mark_preview_maker_stage,
    preview_index_matches_source,
    preview_key,
    preview_step,
    preview_vtt,
    renew_preview_queue_lock,
    start_poster_queue_lock,
)
from file_storage.backends.local import LocalStorageBackend
from models import ProcessingStageType
from tests.fixtures.factories import create_mock_recording


@pytest.fixture(autouse=True)
def mock_preview_maker_persistence(mocker):
    """Endpoint tests use fake recordings, without a PostgreSQL session."""
    mocker.patch("api.services.video_previews.mark_preview_maker_stage", new=AsyncMock(return_value=True))


@pytest.mark.unit
def test_storyboard_cues_stay_bounded_for_long_video() -> None:
    duration = 4 * 3600
    step = preview_step(duration)
    cues = preview_vtt(duration, step)

    assert step == 48
    assert cues.count("#xywh=") == 300
    assert "preview/0.jpg#xywh=0,0,320,180" in cues
    assert "preview/2.jpg#xywh=2880,1620,320,180" in cues
    assert "03:59:12.000 --> 04:00:00.000" in cues


@pytest.mark.unit
def test_ffmpeg_produces_sheet_for_video_shorter_than_interval(tmp_path) -> None:
    from api.tasks.processing import _preview_ffmpeg_command

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        pytest.skip("FFmpeg or ffprobe is not installed")
    source = tmp_path / "short.mp4"
    output = tmp_path / "sprite-%03d.jpg"
    subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=2",
            "-t",
            "4",
            "-c:v",
            "mpeg4",
            "-y",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    command = _preview_ffmpeg_command(source, output, preview_step(4.0), 4.0, keyframes_only=True)
    assert command.index("-skip_frame") < command.index("-i")
    command[0] = ffmpeg_path
    subprocess.run(command, check=True, capture_output=True)

    sheets = list(tmp_path.glob("sprite-*.jpg"))
    assert len(sheets) == 1
    assert sheets[0].stat().st_size > 0
    dimensions = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(sheets[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert dimensions.stdout.strip() == "3200,1800"


@pytest.mark.unit
@pytest.mark.parametrize(("gop", "fast_path"), [(5, True), (100, False)])
async def test_keyframe_probe_selects_safe_extraction_mode(tmp_path, gop: int, fast_path: bool) -> None:
    from api.tasks.processing import _preview_can_skip_nonkey_frames

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg or ffprobe is not installed")
    source = tmp_path / "probe.mp4"
    subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x18:r=1",
            "-t",
            "45",
            "-c:v",
            "mpeg4",
            "-g",
            str(gop),
            "-y",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    assert await _preview_can_skip_nonkey_frames(source, 45.0, 20) is fast_path


@pytest.mark.unit
def test_ffmpeg_limits_sheet_count_to_vtt_cues(tmp_path) -> None:
    from api.tasks.processing import _preview_ffmpeg_command

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        pytest.skip("FFmpeg is not installed")
    source = tmp_path / "long.mp4"
    output = tmp_path / "sprite-%03d.jpg"
    subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=1/20",
            "-t",
            "2020",
            "-c:v",
            "mpeg4",
            "-y",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    command = _preview_ffmpeg_command(source, output, preview_step(2020.0), 2020.0)
    command[0] = ffmpeg_path
    subprocess.run(command, check=True, capture_output=True)

    sheets = sorted(tmp_path.glob("sprite-*.jpg"))
    assert len(sheets) == 2
    assert all(sheet.stat().st_size > 0 for sheet in sheets)


@pytest.mark.unit
def test_ready_storyboard_is_served_after_share_access_check(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    check = mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=True)
    storage.load = AsyncMock(return_value=b"WEBVTT\n")
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    mocker.patch("api.services.video_previews.preview_index_matches_source", new=AsyncMock(return_value=True))

    token = uuid.uuid4()
    response = client.get(f"/api/v1/share/{token}/preview.vtt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/vtt")
    assert response.text == "WEBVTT\n"
    check.assert_awaited_once()


@pytest.mark.unit
def test_stale_storyboard_is_not_served_and_is_rebuilt(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=True)
    storage.load = AsyncMock(return_value=b"OLD WEBVTT")
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    mocker.patch("api.services.video_previews.preview_index_matches_source", new=AsyncMock(return_value=False))
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    mocker.patch("api.dependencies.get_redis", new=AsyncMock(return_value=redis))
    task = mocker.patch("api.tasks.processing.generate_video_previews")

    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview.vtt")

    assert response.status_code == 202
    storage.load.assert_not_awaited()
    assert task.delay.call_args.args[:3] == (8, recording.user_id, True)


@pytest.mark.unit
def test_missing_storyboard_is_queued_once_and_returns_retry(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=[True, False])
    mocker.patch("api.dependencies.get_redis", new=AsyncMock(return_value=redis))
    task = mocker.patch("api.tasks.processing.generate_video_previews")

    token = uuid.uuid4()
    first = client.get(f"/api/v1/share/{token}/preview.vtt")
    second = client.get(f"/api/v1/share/{token}/preview.vtt")

    assert first.status_code == second.status_code == 202
    assert first.headers["retry-after"] == "5"
    task.delay.assert_called_once()
    assert task.delay.call_args.args[:3] == (recording.id, recording.user_id, False)


@pytest.mark.unit
def test_missing_storyboard_does_not_queue_without_deduplication(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    mocker.patch("api.dependencies.get_redis", new=AsyncMock(side_effect=ConnectionError("Redis unavailable")))
    task = mocker.patch("api.tasks.processing.generate_video_previews")

    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview.vtt")

    assert response.status_code == 202
    task.delay.assert_not_called()


@pytest.mark.unit
def test_failed_queue_releases_preview_lock(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock()
    mocker.patch("api.dependencies.get_redis", new=AsyncMock(return_value=redis))
    task = mocker.patch("api.tasks.processing.generate_video_previews")
    task.delay.side_effect = ConnectionError("Queue unavailable")

    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview.vtt")

    assert response.status_code == 202
    redis.eval.assert_awaited_once()
    assert redis.eval.await_args.args[2:] == ("share:preview:8", redis.set.await_args.args[1])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_trim_and_public_request_share_one_queue_lock(client, mocker) -> None:
    from api.tasks.processing import _queue_video_previews

    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=[True, False])
    mocker.patch("api.dependencies.get_redis", new=AsyncMock(return_value=redis))
    redis_factory = mocker.patch("redis.asyncio.from_url")
    redis_factory.return_value.__aenter__ = AsyncMock(return_value=redis)
    redis_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    task = mocker.patch("api.tasks.processing.generate_video_previews")

    assert await _queue_video_previews(recording.id, recording.user_id, force=True)
    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview.vtt")

    assert response.status_code == 202
    assert redis.set.await_count == 2
    task.delay.assert_called_once()
    assert task.delay.call_args.args[:3] == (recording.id, recording.user_id, True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_publishes_outside_event_loop(mocker) -> None:
    from api.services.video_previews import enqueue_video_previews

    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    task = mocker.patch("api.tasks.processing.generate_video_previews")
    publish_threads: list[int] = []
    task.delay.side_effect = lambda *_args: publish_threads.append(threading.get_ident())

    assert await enqueue_video_previews(redis, 8, "owner")
    assert len(publish_threads) == 1
    assert publish_threads[0] != threading.get_ident()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_requests_share_a_single_queue_claim(mocker) -> None:
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=[True, False])
    task = mocker.patch("api.tasks.processing.generate_poster")

    assert await enqueue_poster(redis, 8, "owner")
    assert not await enqueue_poster(redis, 8, "owner")
    task.delay.assert_called_once()
    assert task.delay.call_args.args[:2] == (8, "owner")
    assert redis.set.await_args_list[0].args[0] == "share:poster:8"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_poster_publish_releases_claim(mocker) -> None:
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock()
    task = mocker.patch("api.tasks.processing.generate_poster")
    task.delay.side_effect = ConnectionError("broker unavailable")

    with pytest.raises(ConnectionError, match="broker unavailable"):
        await enqueue_poster(redis, 8, "owner")
    assert redis.eval.await_args.args[2] == "share:poster:8"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_lock_renewal_requires_matching_token() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(side_effect=[1, 0])

    assert await renew_preview_queue_lock(redis, 8, "owner-token")
    assert not await renew_preview_queue_lock(redis, 8, "old-token")
    assert redis.eval.await_args_list[0].args[2:] == ("share:preview:8", "owner-token", 3900)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expired_queue_claim_can_be_reclaimed_only_by_its_message() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(side_effect=[1, 0])

    assert await claim_preview_queue_lock(redis, 8, "queued-token")
    assert not await claim_preview_queue_lock(redis, 8, "stale-token")
    assert redis.eval.await_args_list[0].args[2:] == ("share:preview:8", "queued-token", 3900)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_poster_run_claim_rejects_duplicate_delivery() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(side_effect=[1, 0])

    assert await start_poster_queue_lock(redis, 8, "queued-token")
    assert not await start_poster_queue_lock(redis, 8, "queued-token")
    assert redis.eval.await_args_list[0].args[2:] == ("share:poster:8", "queued-token", "queued-token:running", 3900)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ffmpeg_timeout_kills_and_reaps_child_process() -> None:
    from api.tasks.processing import _communicate_preview_ffmpeg

    process = MagicMock(returncode=None)
    calls = 0

    async def communicate():
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(1)
        return b"", b""

    process.communicate = communicate

    with pytest.raises(TimeoutError):
        await _communicate_preview_ffmpeg(process, timeout=0.001)
    process.kill.assert_called_once()
    assert calls == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_maker_stage_tracks_source_and_rejects_stale_completion(mocker) -> None:
    trim_completed = datetime.now(UTC)
    recording = create_mock_recording(
        record_id=8,
        processed_video_path="video.mp4",
        processing_stages=[MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=trim_completed)],
    )
    session = MagicMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session_factory = mocker.patch("api.dependencies.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.repositories.recording_repos.RecordingRepository").return_value.get_by_id = AsyncMock(
        return_value=recording
    )

    assert await mark_preview_maker_stage(8, recording.user_id, "PENDING", "token")
    stage = session.add.call_args.args[0]
    assert stage.status == "PENDING"
    assert stage.source_video_path == "video.mp4"
    assert stage.source_trimmed_at == trim_completed

    session.get = AsyncMock(return_value=stage)
    assert await mark_preview_maker_stage(8, recording.user_id, "IN_PROGRESS", "token")
    assert stage.status == "IN_PROGRESS"
    assert await mark_preview_maker_stage(8, recording.user_id, "IN_PROGRESS", "token") is None
    assert stage.status == "IN_PROGRESS"
    assert not await mark_preview_maker_stage(
        8, recording.user_id, "PENDING", "recovery", expected_run_token="newer-token"
    )
    assert stage.run_token == "token"

    recording.processing_stages[0].completed_at = trim_completed + timedelta(seconds=1)
    assert not await mark_preview_maker_stage(8, recording.user_id, "COMPLETED", "token")
    assert stage.status == "IN_PROGRESS"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_index_requires_completed_stage_for_same_trim(mocker) -> None:
    trimmed_at = datetime.now(UTC)
    recording = create_mock_recording(
        record_id=8,
        processed_video_path="video.mp4",
        processing_stages=[],
    )
    session = MagicMock()
    result = MagicMock()
    result.one_or_none.side_effect = [
        ("COMPLETED", "video.mp4", trimmed_at, "video.mp4", trimmed_at),
        ("COMPLETED", "video.mp4", trimmed_at, "video.mp4", trimmed_at + timedelta(seconds=1)),
    ]
    session.execute = AsyncMock(return_value=result)
    session_factory = mocker.patch("api.dependencies.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)

    assert await preview_index_matches_source(recording)
    assert not await preview_index_matches_source(recording)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_preview_has_cooldown_but_new_trim_or_manual_force_can_retry(mocker) -> None:
    trimmed_at = datetime.now(UTC)
    recording = create_mock_recording(
        record_id=8,
        processed_video_path="video.mp4",
        processing_stages=[MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=trimmed_at)],
    )
    stage = MagicMock(
        status="FAILED",
        source_video_path="video.mp4",
        source_trimmed_at=trimmed_at,
        failed_at=datetime.now(UTC),
        attempt_count=1,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=stage)
    session.commit = AsyncMock()
    session_factory = mocker.patch("api.dependencies.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.repositories.recording_repos.RecordingRepository").return_value.get_by_id = AsyncMock(
        return_value=recording
    )

    assert not await mark_preview_maker_stage(8, recording.user_id, "PENDING", "retry")
    session.commit.assert_not_awaited()

    assert await mark_preview_maker_stage(8, recording.user_id, "PENDING", "manual", ignore_failure_cooldown=True)
    assert stage.status == "PENDING"
    assert stage.run_token == "manual"
    assert stage.attempt_count == 2
    assert stage.queued_at is not None

    stage.status = "FAILED"
    stage.failed_at = datetime.now(UTC)
    stage.attempt_count = 3
    assert not await mark_preview_maker_stage(8, recording.user_id, "PENDING", "automatic-fourth")
    recording.processing_stages[0].completed_at = trimmed_at + timedelta(seconds=1)
    assert await mark_preview_maker_stage(8, recording.user_id, "PENDING", "new-trim")
    assert stage.run_token == "new-trim"
    assert stage.attempt_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_storyboard_uses_processed_file_duration_not_recording_metadata(mocker, tmp_path) -> None:
    from api.tasks.processing import _async_generate_video_previews

    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    recording.duration = 3600
    recording.final_duration = None
    recording.updated_at = datetime.now(UTC)
    session = MagicMock()
    session.execute = AsyncMock()
    session_factory = mocker.patch("api.tasks.processing.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.processing.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=recording)
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    storage.save = AsyncMock()
    storage.save_file = AsyncMock()

    async def download(_key, target):
        target.write_bytes(b"processed video")

    storage.download_to_file = AsyncMock(side_effect=download)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    builder = mocker.patch("file_storage.path_builder.get_path_builder").return_value
    builder.temp_dir.return_value = tmp_path
    builder.recording_root.return_value = Path("storage/users/user_000001/recordings/8")
    probe = mocker.patch("video_processing_module.audio_detector.AudioDetector.get_duration_seconds")
    probe.return_value = 40.0

    async def ffmpeg(*args, **_kwargs):
        Path(args[-1].replace("%03d", "000")).write_bytes(b"jpeg")
        process = MagicMock(returncode=0)
        process.communicate = AsyncMock(return_value=(b"", b""))
        return process

    spawn = mocker.patch("asyncio.create_subprocess_exec", side_effect=ffmpeg)

    result = await _async_generate_video_previews(recording.id, recording.user_id)

    assert result == {"success": True, "sheets": 1}
    probe.assert_awaited_once()
    poster_key = storage.save_file.await_args_list[-1].args[0]
    assert poster_key.endswith("/recordings/8/poster.jpg")
    poster_args = spawn.await_args_list[-1].args
    assert float(poster_args[poster_args.index("-ss") + 1]) == 20.0
    vtt = storage.save.await_args.args[1].decode()
    assert "00:00:20.000 --> 00:00:40.000" in vtt
    assert "01:00:00.000" not in vtt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_storyboard_does_not_publish_after_recording_changes(mocker, tmp_path) -> None:
    from api.tasks.processing import _async_generate_video_previews

    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    first_trim = datetime.now(UTC)
    recording.processing_stages = [MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=first_trim)]
    changed = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    changed.processing_stages = [
        MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=first_trim + timedelta(seconds=1))
    ]
    session = MagicMock()
    session_factory = mocker.patch("api.tasks.processing.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.processing.RecordingRepository").return_value.get_by_id = AsyncMock(
        side_effect=[recording, changed]
    )
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    storage.save = AsyncMock()
    storage.save_file = AsyncMock()

    async def download(_key, target):
        target.write_bytes(b"processed video")

    storage.download_to_file = AsyncMock(side_effect=download)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    mocker.patch("file_storage.path_builder.get_path_builder").return_value.temp_dir.return_value = tmp_path
    mocker.patch("video_processing_module.audio_detector.AudioDetector.get_duration_seconds", return_value=40.0)

    async def ffmpeg(*args, **_kwargs):
        Path(args[-1].replace("%03d", "000")).write_bytes(b"jpeg")
        process = MagicMock(returncode=0)
        process.communicate = AsyncMock(return_value=(b"", b""))
        return process

    mocker.patch("asyncio.create_subprocess_exec", side_effect=ffmpeg)

    result = await _async_generate_video_previews(recording.id, recording.user_id)

    assert result == {"success": False, "stale": True}
    storage.save.assert_not_awaited()
    storage.save_file.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_storyboard_rechecks_source_before_final_publication(mocker, tmp_path) -> None:
    from api.tasks.processing import _async_generate_video_previews

    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    first_trim = datetime.now(UTC)
    recording.processing_stages = [MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=first_trim)]
    changed = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    changed.processing_stages = [
        MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=first_trim + timedelta(seconds=1))
    ]
    session = MagicMock()
    session.execute = AsyncMock()
    session_factory = mocker.patch("api.tasks.processing.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.processing.RecordingRepository").return_value.get_by_id = AsyncMock(
        side_effect=[recording, recording, recording, changed]
    )
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    storage.save = AsyncMock()
    storage.save_file = AsyncMock()

    async def download(_key, target):
        target.write_bytes(b"processed video")

    storage.download_to_file = AsyncMock(side_effect=download)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    mocker.patch("file_storage.path_builder.get_path_builder").return_value.temp_dir.return_value = tmp_path
    mocker.patch("video_processing_module.audio_detector.AudioDetector.get_duration_seconds", return_value=40.0)

    async def ffmpeg(*args, **_kwargs):
        Path(args[-1].replace("%03d", "000")).write_bytes(b"jpeg")
        process = MagicMock(returncode=0)
        process.communicate = AsyncMock(return_value=(b"", b""))
        return process

    mocker.patch("asyncio.create_subprocess_exec", side_effect=ffmpeg)

    assert await _async_generate_video_previews(recording.id, recording.user_id) == {"success": False, "stale": True}
    assert storage.save_file.await_count == 1  # The sheet is harmless without its VTT index.
    assert storage.save_file.await_args.args[0].endswith("/previews/0.jpg")
    storage.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lost_queue_claim_cannot_invalidate_existing_storyboard(mocker) -> None:
    from api.tasks.processing import _async_generate_video_previews

    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    session = MagicMock()
    session_factory = mocker.patch("api.tasks.processing.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.processing.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=recording)
    storage = MagicMock()
    storage.delete = AsyncMock()
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)

    assert await _async_generate_video_previews(
        8, recording.user_id, force=True, check_lock=AsyncMock(return_value=False)
    ) == {
        "success": False,
        "stale": True,
    }
    storage.delete.assert_not_awaited()


@pytest.mark.unit
def test_duplicate_poster_delivery_keeps_running_workers_claim(mocker) -> None:
    from api.tasks.processing import generate_poster

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        return False

    mocker.patch.object(generate_poster, "run_async", side_effect=run_async)

    assert generate_poster.run(8, "owner", "queue-token") == {
        "success": True,
        "skipped": "newer or running poster task",
    }
    assert calls == ["_start_poster_queue_lock"]


@pytest.mark.unit
def test_poster_worker_releases_its_claim_after_generation(mocker) -> None:
    from api.tasks.processing import generate_poster

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        return True if calls[-1] == "_start_poster_queue_lock" else {"success": True}

    mocker.patch.object(generate_poster, "run_async", side_effect=run_async)

    assert generate_poster.run(8, "owner", "queue-token") == {"success": True}
    assert calls == ["_start_poster_queue_lock", "_async_generate_poster", "_release_poster_queue_lock"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_poster_cannot_overwrite_after_retrim(mocker, tmp_path) -> None:
    from api.tasks.processing import _async_generate_poster

    first_trim = datetime.now(UTC)
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    recording.processing_stages = [MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=first_trim)]
    changed = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    changed.processing_stages = [
        MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=first_trim + timedelta(seconds=1))
    ]
    session = MagicMock()
    session.execute = AsyncMock()
    session_factory = mocker.patch("api.tasks.processing.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.processing.RecordingRepository").return_value.get_by_id = AsyncMock(
        side_effect=[recording, changed]
    )
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=False)
    storage.save_file = AsyncMock()

    async def download(_key, target):
        target.write_bytes(b"video")

    storage.download_to_file = AsyncMock(side_effect=download)
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)
    builder = mocker.patch("file_storage.path_builder.get_path_builder").return_value
    builder.recording_root.return_value = Path("storage/users/user_000001/recordings/8")
    builder.create_temp_file.side_effect = [tmp_path / "source.mp4", tmp_path / "poster.jpg"]
    mocker.patch("video_processing_module.audio_detector.AudioDetector.get_duration_seconds", return_value=40.0)
    mocker.patch("api.tasks.processing._extract_midpoint_poster", new=AsyncMock())

    assert await _async_generate_poster(8, recording.user_id) == {"success": False, "stale": True}
    storage.save_file.assert_not_awaited()


@pytest.mark.unit
def test_preview_revision_ignores_view_counter_updates() -> None:
    from api.tasks.processing import _preview_source_revision

    trimmed_at = datetime.now(UTC)
    recording = create_mock_recording(
        processed_video_path="video.mp4",
        processing_stages=[MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=trimmed_at)],
    )
    viewed = create_mock_recording(
        processed_video_path="video.mp4",
        processing_stages=[MagicMock(stage_type=ProcessingStageType.TRIM, completed_at=trimmed_at)],
        updated_at=recording.updated_at + timedelta(seconds=1),
    )

    assert _preview_source_revision(recording) == _preview_source_revision(viewed)


@pytest.mark.unit
def test_changed_video_releases_lock_then_queues_fresh_generation(mocker) -> None:
    from api.tasks.processing import generate_video_previews

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        if calls[-1] in ("_claim_video_preview_lock", "_set_preview_maker_stage"):
            return True
        return {"success": False, "stale": True} if calls[-1] == "_run_video_preview_job" else None

    mocker.patch.object(generate_video_previews, "run_async", side_effect=run_async)

    result = generate_video_previews.run(8, "owner", True, "queue-token")

    assert result == {"success": False, "stale": True}
    assert calls == [
        "_claim_video_preview_lock",
        "_set_preview_maker_stage",
        "_run_video_preview_job",
        "_release_video_preview_lock",
        "_queue_video_previews",
    ]


@pytest.mark.unit
def test_stale_queued_message_never_starts_generation(mocker) -> None:
    from api.tasks.processing import generate_video_previews

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        return False

    mocker.patch.object(generate_video_previews, "run_async", side_effect=run_async)

    assert generate_video_previews.run(8, "owner", True, "old-token") == {"success": False, "stale": True}
    assert calls == ["_claim_video_preview_lock"]


@pytest.mark.unit
def test_redelivered_preview_keeps_original_workers_lock(mocker) -> None:
    from api.tasks.processing import generate_video_previews

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        return True if calls[-1] == "_claim_video_preview_lock" else None

    mocker.patch.object(generate_video_previews, "run_async", side_effect=run_async)

    assert generate_video_previews.run(8, "owner", True, "queue-token") == {"success": False, "stale": True}
    assert calls == ["_claim_video_preview_lock", "_set_preview_maker_stage"]


@pytest.mark.unit
def test_changed_source_before_start_requeues_after_releasing_claim(mocker) -> None:
    from api.tasks.processing import generate_video_previews

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        return calls[-1] == "_claim_video_preview_lock"

    mocker.patch.object(generate_video_previews, "run_async", side_effect=run_async)

    assert generate_video_previews.run(8, "owner", True, "old-token") == {"success": False, "stale": True}
    assert calls == ["_claim_video_preview_lock", "_set_preview_maker_stage", "_release_video_preview_lock"]


@pytest.mark.unit
def test_preview_ffmpeg_failure_marks_celery_task_failed_without_failing_main_chain(mocker) -> None:
    from api.tasks.processing import generate_video_previews

    calls = []

    def run_async(coro):
        calls.append(coro.cr_code.co_name)
        coro.close()
        if calls[-1] in ("_claim_video_preview_lock", "_set_preview_maker_stage"):
            return True
        if calls[-1] == "_run_video_preview_job":
            raise RuntimeError("ffmpeg failed")
        return None

    mocker.patch.object(generate_video_previews, "run_async", side_effect=run_async)

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        generate_video_previews.run(8, "owner", True, "queue-token")
    assert calls == [
        "_claim_video_preview_lock",
        "_set_preview_maker_stage",
        "_run_video_preview_job",
        "_set_preview_maker_stage",
        "_release_video_preview_lock",
    ]


@pytest.mark.unit
def test_preview_dispatch_failure_keeps_main_chain_alive(mocker) -> None:
    from api.tasks.processing import enqueue_video_previews_task

    def fail(coro):
        coro.close()
        raise ConnectionError("Redis unavailable")

    mocker.patch.object(enqueue_video_previews_task, "run_async", side_effect=fail)

    assert enqueue_video_previews_task.run({"result": {"success": True}}, 8, "owner") == {
        "success": True,
        "queued": False,
        "preview_error": "Redis unavailable",
    }


@pytest.mark.unit
def test_preview_dispatch_skips_completed_trim(mocker) -> None:
    from api.tasks.processing import enqueue_video_previews_task

    queue = mocker.patch.object(enqueue_video_previews_task, "run_async")

    assert enqueue_video_previews_task.run({"result": {"status": "skipped"}}, 8, "owner") == {
        "success": True,
        "queued": False,
        "reason": "trim did not produce a new video",
    }
    queue.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_dispatch_requires_processed_video(mocker) -> None:
    from api.tasks.processing import _enqueue_processed_video_previews

    recording = create_mock_recording(record_id=8, processed_video_path=None)
    session = MagicMock()
    session_factory = mocker.patch("api.tasks.processing.get_async_session_maker")
    session_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.processing.RecordingRepository").return_value.get_by_id = AsyncMock(return_value=recording)
    queue = mocker.patch("api.tasks.processing._queue_video_previews", new_callable=AsyncMock)

    assert not await _enqueue_processed_video_previews(8, "owner")
    queue.assert_not_awaited()


@pytest.mark.unit
def test_revoked_share_cannot_fetch_preview_sheet(client, mocker) -> None:
    mocker.patch(
        "api.routers.share._get_recording_by_share_token",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Share link not found")),
    )
    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview/0.jpg")
    assert response.status_code == 404


@pytest.mark.unit
def test_old_sheet_is_hidden_after_source_changes(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    mocker.patch("api.services.video_previews.preview_index_matches_source", new=AsyncMock(return_value=False))
    storage = mocker.patch("file_storage.factory.get_storage_backend")

    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview/0.jpg")

    assert response.status_code == 404
    storage.assert_not_called()


@pytest.mark.unit
def test_public_share_serves_local_preview_without_owner_login(client, mocker, tmp_path) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    mocker.patch("api.services.video_previews.preview_index_matches_source", new=AsyncMock(return_value=True))
    storage = LocalStorageBackend(base_path=tmp_path)
    sheet = storage._resolve(preview_key(1, 8, "0.jpg"))
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"\xff\xd8\xff\xd9")
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)

    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview/0.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"\xff\xd8\xff\xd9"


@pytest.mark.unit
def test_public_share_signs_s3_preview_sheet(client, mocker) -> None:
    recording = create_mock_recording(record_id=8, processed_video_path="video.mp4")
    recording.owner = MagicMock(user_slug=1)
    mocker.patch("api.routers.share._get_recording_by_share_token", new=AsyncMock(return_value=recording))
    mocker.patch("api.services.video_previews.preview_index_matches_source", new=AsyncMock(return_value=True))
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=True)
    storage.presigned_url = AsyncMock(return_value="https://storage.example/preview.jpg")
    mocker.patch("file_storage.factory.get_storage_backend", return_value=storage)

    response = client.get(f"/api/v1/share/{uuid.uuid4()}/preview/0.jpg", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://storage.example/preview.jpg"


@pytest.mark.unit
def test_playlist_preview_requires_public_item_access(client, mocker) -> None:
    lookup = mocker.patch(
        "api.routers.share._public_playlist_item_or_404",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Share link not found")),
    )
    storage = mocker.patch("file_storage.factory.get_storage_backend")

    token = uuid.uuid4()
    response = client.get(f"/api/v1/share/p/{token}/items/42/preview.vtt")

    assert response.status_code == 404
    lookup.assert_awaited_once()
    storage.assert_not_called()


@pytest.mark.unit
def test_owner_preview_lookup_is_scoped_to_user(client, mocker, mock_user) -> None:
    lookup = AsyncMock(return_value=None)
    mocker.patch("api.routers.recordings.RecordingRepository").return_value.get_by_id = lookup

    response = client.get("/api/v1/recordings/8/preview.vtt")

    assert response.status_code == 404
    lookup.assert_awaited_once_with(8, mock_user.id)
