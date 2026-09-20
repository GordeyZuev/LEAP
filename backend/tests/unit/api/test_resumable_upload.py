"""Resume and finalize interrupted local video uploads."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.core.context import ServiceContext
from api.routers.recordings import append_resumable_chunk, complete_resumable_upload
from api.schemas.recording.operations import LocalRecordingUploadResponse
from api.schemas.recording.request import AddVideoByUrlRequest
from api.services.resumable_upload import create_session, read_session, session_status


def _request(body: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": "PUT", "headers": [(b"content-length", str(len(body)).encode())]}, receive
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_resumes_from_server_offset_and_is_owner_scoped(mocker, tmp_path):
    mocker.patch("api.services.resumable_upload.upload_dir", return_value=tmp_path)
    session = create_session("owner", "lecture.mp4", 8, "Lecture", False, "a" * 64)
    upload_id = session["upload_id"]
    ctx = ServiceContext(session=AsyncMock(), user_id="owner")

    first = await append_resumable_chunk(upload_id, _request(b"abcd"), offset=0, ctx=ctx)
    assert first["offset"] == 4
    with pytest.raises(HTTPException) as conflict:
        await append_resumable_chunk(upload_id, _request(b"abcd"), offset=0, ctx=ctx)
    assert conflict.value.status_code == 409

    resumed = await append_resumable_chunk(upload_id, _request(b"efgh"), offset=4, ctx=ctx)
    assert resumed["offset"] == 8
    assert (tmp_path / f"{upload_id}.part").read_bytes() == b"abcdefgh"
    with pytest.raises(HTTPException) as hidden:
        read_session(upload_id, "someone-else")
    assert hidden.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interrupted_chunk_keeps_received_bytes_for_resume(mocker, tmp_path):
    mocker.patch("api.services.resumable_upload.upload_dir", return_value=tmp_path)
    session = create_session("owner", "lecture.mp4", 4, "Lecture", False, "c" * 64)
    upload_id = session["upload_id"]
    ctx = ServiceContext(session=AsyncMock(), user_id="owner")
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b"ab", "more_body": True}
        raise ConnectionError("connection lost")

    request = Request({"type": "http", "method": "PUT", "headers": []}, receive)
    with pytest.raises(ConnectionError):
        await append_resumable_chunk(upload_id, request, offset=0, ctx=ctx)

    data, part_path = read_session(upload_id, "owner")
    assert session_status(data, part_path)["offset"] == 2
    resumed = await append_resumable_chunk(upload_id, _request(b"cd"), offset=2, ctx=ctx)
    assert resumed["offset"] == 4
    assert part_path.read_bytes() == b"abcd"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oversize_chunk_does_not_corrupt_saved_offset(mocker, tmp_path):
    mocker.patch("api.services.resumable_upload.upload_dir", return_value=tmp_path)
    session = create_session("owner", "lecture.mp4", 4, "Lecture", False, "d" * 64)
    upload_id = session["upload_id"]
    ctx = ServiceContext(session=AsyncMock(), user_id="owner")
    await append_resumable_chunk(upload_id, _request(b"abc"), offset=0, ctx=ctx)

    with pytest.raises(HTTPException) as error:
        await append_resumable_chunk(upload_id, _request(b"xy"), offset=3, ctx=ctx)

    assert error.value.status_code == 413
    data, part_path = read_session(upload_id, "owner")
    assert session_status(data, part_path)["offset"] == 3
    assert part_path.read_bytes() == b"abc"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_completion_is_idempotent_after_response_is_lost(mocker, tmp_path):
    mocker.patch("api.services.resumable_upload.upload_dir", return_value=tmp_path)
    session = create_session("owner", "lecture.mp4", 4, "Lecture", True, "b" * 64)
    upload_id = session["upload_id"]
    (tmp_path / f"{upload_id}.part").write_bytes(b"data")
    repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
    repo.find_by_source_key = AsyncMock(
        side_effect=[
            None,
            SimpleNamespace(id=7, display_name="Lecture", local_video_path="users/1/recordings/7/source.mp4"),
        ]
    )
    finalize = mocker.patch(
        "api.routers.recordings._finalize_local_video",
        new=AsyncMock(
            return_value=LocalRecordingUploadResponse(
                success=True,
                recording_id=7,
                display_name="Lecture",
                local_video_path="users/1/recordings/7/source.mp4",
                task_id="task-7",
                auto_run_requested=True,
            )
        ),
    )
    ctx = ServiceContext(session=AsyncMock(), user_id="owner")
    current_user = SimpleNamespace(id="owner")
    quota_check = mocker.patch("api.routers.recordings.check_user_quotas", new=AsyncMock())

    first = await complete_resumable_upload(upload_id, ctx=ctx, current_user=current_user)
    retried = await complete_resumable_upload(upload_id, ctx=ctx, current_user=current_user)

    assert first.recording_id == retried.recording_id == 7
    assert retried.task_id == "task-7"
    quota_check.assert_awaited_once_with(current_user, ctx.session)
    finalize.assert_awaited_once()
    assert finalize.await_args.kwargs["source_key"] == f"local_owner_{upload_id}"
    data, part_path = read_session(upload_id, "owner")
    assert session_status(data, part_path)["offset"] == 4
    assert not part_path.exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_completion_checks_quota_before_creating_recording(mocker, tmp_path):
    mocker.patch("api.services.resumable_upload.upload_dir", return_value=tmp_path)
    session = create_session("owner", "lecture.mp4", 4, "Lecture", False, "e" * 64)
    upload_id = session["upload_id"]
    (tmp_path / f"{upload_id}.part").write_bytes(b"data")
    repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
    repo.find_by_source_key = AsyncMock(return_value=None)
    quota_check = mocker.patch(
        "api.routers.recordings.check_user_quotas",
        new=AsyncMock(side_effect=HTTPException(status_code=429, detail="Monthly quota exceeded")),
    )
    finalize = mocker.patch("api.routers.recordings._finalize_local_video", new=AsyncMock())
    ctx = ServiceContext(session=AsyncMock(), user_id="owner")
    current_user = SimpleNamespace(id="owner")

    with pytest.raises(HTTPException) as error:
        await complete_resumable_upload(upload_id, ctx=ctx, current_user=current_user)

    assert error.value.status_code == 429
    quota_check.assert_awaited_once_with(current_user, ctx.session)
    finalize.assert_not_awaited()


@pytest.mark.unit
def test_available_quality_accepts_actual_video_resolutions(mocker):
    mocker.patch("api.schemas.recording.request.validate_public_url", side_effect=lambda url, **_: url)
    assert (
        AddVideoByUrlRequest.model_validate(
            {"url": "https://www.youtube.com/watch?v=abcdefghijk", "quality": "1440p"}
        ).quality
        == "1440p"
    )
    with pytest.raises(ValueError):
        AddVideoByUrlRequest.model_validate({"url": "https://www.youtube.com/watch?v=abcdefghijk", "quality": "9999p"})
