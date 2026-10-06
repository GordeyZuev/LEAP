"""Regression checks for video ingestion and reset semantics."""

from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from api.core.context import ServiceContext
from api.repositories.recording_repos import RecordingRepository
from api.routers.input_sources import _sync_yandex_disk_source
from api.routers.recordings import (
    add_local_recording,
    add_playlist_by_url,
    add_public_disk_link,
    add_video_by_url,
    get_upload_policy,
    preview_playlist,
    preview_public_disk_link,
    reset_recording,
)
from api.schemas.recording.request import (
    AddPlaylistByUrlRequest,
    AddPublicDiskLinkRequest,
    AddVideoByUrlRequest,
    FormatsPreviewRequest,
    PublicDiskLinkRequest,
)
from api.tasks.sync_tasks import _async_batch_sync_sources, _queue_new_recordings
from models.recording import ProcessingStatus, SourceType


@pytest.mark.unit
class TestRecordingIngress:
    @pytest.mark.asyncio
    async def test_upload_policy_uses_configured_limit_and_formats(self, mocker):
        mocker.patch(
            "api.routers.recordings.get_settings",
            return_value=SimpleNamespace(
                storage=SimpleNamespace(max_upload_size_mb=128, supported_video_formats=["mp4"])
            ),
        )

        policy = await get_upload_policy(_ctx=ServiceContext(session=AsyncMock(), user_id="user"))

        assert policy["max_upload_bytes"] == 128 * 1024 * 1024
        assert ".mp4" in policy["extensions"]
        assert policy["resume_hours"] == 24

    @pytest.mark.asyncio
    async def test_local_upload_rejects_oversize_and_cleans_temp(self, mocker, tmp_path):
        temp_path = tmp_path / "upload.mp4"
        mocker.patch("api.routers.recordings.StoragePathBuilder.create_temp_file", return_value=temp_path)
        mocker.patch(
            "api.routers.recordings.get_settings",
            return_value=SimpleNamespace(
                storage=SimpleNamespace(max_upload_size_mb=1, supported_video_formats=["mp4"])
            ),
        )
        ctx = ServiceContext(session=AsyncMock(), user_id="user")
        upload = UploadFile(file=BytesIO(b"a" * (1024 * 1024 + 1)), filename="lecture.mp4")

        with pytest.raises(HTTPException) as exc:
            await add_local_recording(file=upload, display_name="Lecture", ctx=ctx, _quota=None)

        assert exc.value.status_code == 413
        assert not temp_path.exists()

    @pytest.mark.asyncio
    async def test_local_upload_rejects_bad_media_as_client_error(self, mocker, tmp_path):
        temp_path = tmp_path / "upload.mp4"
        mocker.patch("api.routers.recordings.StoragePathBuilder.create_temp_file", return_value=temp_path)
        mocker.patch(
            "api.routers.recordings.get_settings",
            return_value=SimpleNamespace(
                storage=SimpleNamespace(max_upload_size_mb=1, supported_video_formats=["mp4"])
            ),
        )
        ctx = ServiceContext(session=AsyncMock(), user_id="user")
        upload = UploadFile(file=BytesIO(b"not a video" * 200), filename="lecture.mp4")

        with pytest.raises(HTTPException) as exc:
            await add_local_recording(file=upload, display_name="Lecture", ctx=ctx, _quota=None)

        assert exc.value.status_code == 400
        assert not temp_path.exists()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("auto_run", [False, True])
    async def test_local_upload_stores_normalized_name_and_duration(self, mocker, tmp_path, auto_run):
        temp_path = tmp_path / "upload.mp4"
        mocker.patch("api.routers.recordings.StoragePathBuilder.create_temp_file", return_value=temp_path)
        mocker.patch("api.routers.recordings.ingress_validate_saved_media", return_value=True)
        mocker.patch("api.routers.recordings.AudioDetector").return_value.get_duration_seconds = AsyncMock(
            return_value=73.8
        )
        mocker.patch(
            "api.routers.recordings.get_settings",
            return_value=SimpleNamespace(
                storage=SimpleNamespace(max_upload_size_mb=1, supported_video_formats=["mp4"])
            ),
        )
        mocker.patch("api.routers.recordings._track_recordings_created", new=AsyncMock())
        queue = mocker.patch("api.routers.recordings._auto_run_recording", new=AsyncMock(return_value="task-7"))
        quota = mocker.patch("api.routers.recordings.QuotaService").return_value
        quota.check_storage_quota = AsyncMock(return_value=(True, None))
        repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
        recording = SimpleNamespace(id=7, display_name="Lecture 1", local_video_path=None)
        repo.create = AsyncMock(return_value=recording)
        config = mocker.patch("api.routers.recordings.UserConfigRepository").return_value
        config.get_effective_config = AsyncMock(return_value={})
        storage = mocker.patch("file_storage.factory.get_storage_backend").return_value
        storage.save_file = AsyncMock()
        ctx = ServiceContext(session=AsyncMock(), user_id="user")
        ctx.session.execute.return_value = MagicMock()
        ctx.session.execute.return_value.scalar_one.return_value = SimpleNamespace(user_slug=42)
        upload = UploadFile(file=BytesIO(b"a" * 2048), filename="lecture.mp4")

        result = await add_local_recording(
            file=upload, display_name="  Lecture  \n 1 ", ctx=ctx, _quota=None, auto_run=auto_run
        )

        assert result.recording_id == 7
        assert result.display_name == "Lecture 1"
        assert repo.create.await_args.kwargs["display_name"] == "Lecture 1"
        assert repo.create.await_args.kwargs["duration"] == 73
        assert recording.local_video_path.endswith("source.mp4")
        assert result.task_id == ("task-7" if auto_run else None)
        assert queue.await_count == int(auto_run)
        assert not temp_path.exists()

    @pytest.mark.asyncio
    async def test_single_url_conflicts_with_existing_recording(self, mocker):
        mocker.patch(
            "video_download_module.platforms.ytdlp.metadata.extract_video_info",
            new=AsyncMock(return_value={"platform": "youtube", "id": "abc", "title": "Lecture"}),
        )
        repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
        repo.find_by_source_key = AsyncMock(return_value=SimpleNamespace(id=42))
        ctx = ServiceContext(session=AsyncMock(), user_id="user")

        with pytest.raises(HTTPException) as exc:
            await add_video_by_url(
                AddVideoByUrlRequest.model_construct(url="https://youtube.com/watch?v=abc"), ctx=ctx, _quota=None
            )

        assert exc.value.status_code == 409
        assert "42" in exc.value.detail
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_disk_name_excludes_extension(self, mocker):
        disk = mocker.patch("yandex_disk_module.client.YandexDiskClient").return_value
        disk.list_video_files = AsyncMock(return_value=[{"name": "Lecture 1.mp4", "path": "/Lecture 1.mp4"}])
        templates = mocker.patch("api.routers.input_sources.RecordingTemplateRepository").return_value
        templates.find_matchable_by_user = AsyncMock(return_value=[])
        config = mocker.patch("api.routers.input_sources.UserConfigRepository").return_value
        config.get_effective_config = AsyncMock(return_value={})
        repo = mocker.patch("api.routers.input_sources.RecordingRepository").return_value
        repo.create_or_update = AsyncMock(return_value=(MagicMock(), True))
        source = SimpleNamespace(id=1, config={"folder_path": "/"})

        result = await _sync_yandex_disk_source(source, {"oauth_token": "test"}, AsyncMock(), "user")

        assert repo.create_or_update.await_args.kwargs["display_name"] == "Lecture 1"
        assert result["new_recording_ids"] == [repo.create_or_update.return_value[0].id]

    @pytest.mark.asyncio
    async def test_public_disk_link_creates_source_and_queues_sync(self, mocker):
        disk = mocker.patch("yandex_disk_module.client.YandexDiskClient").return_value
        disk.get_public_meta = AsyncMock(return_value={"type": "dir"})
        repo = mocker.patch("api.routers.recordings.InputSourceRepository").return_value
        repo.find_by_user = AsyncMock(return_value=[])
        repo.find_duplicate = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=SimpleNamespace(id=17))
        task = mocker.patch(
            "api.tasks.sync_tasks.sync_single_source_task.apply_async", return_value=SimpleNamespace(id="sync-17")
        )
        ctx = ServiceContext(session=AsyncMock(), user_id="user")

        response = await add_public_disk_link(
            AddPublicDiskLinkRequest.model_construct(
                public_url="https://disk.yandex.ru/d/shared", name="Course folder", resource_type="dir", auto_run=True
            ),
            ctx=ctx,
        )

        assert response.source_id == 17
        assert response.reused is False
        assert repo.create.await_args.kwargs["config"]["public_url"] == "https://disk.yandex.ru/d/shared"
        task.assert_called_once_with(kwargs={"source_id": 17, "user_id": "user", "auto_run": True})
        ctx.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_public_disk_link_reuses_existing_source(self, mocker):
        disk = mocker.patch("yandex_disk_module.client.YandexDiskClient").return_value
        disk.get_public_meta = AsyncMock(return_value={"type": "dir"})
        repo = mocker.patch("api.routers.recordings.InputSourceRepository").return_value
        repo.find_by_user = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=17,
                    source_type="YANDEX_DISK",
                    config={"public_url": "https://disk.yandex.ru/d/shared"},
                    is_active=True,
                )
            ]
        )
        mocker.patch(
            "api.tasks.sync_tasks.sync_single_source_task.apply_async", return_value=SimpleNamespace(id="sync-18")
        )
        ctx = ServiceContext(session=AsyncMock(), user_id="user")

        response = await add_public_disk_link(
            AddPublicDiskLinkRequest.model_construct(
                public_url="https://disk.yandex.ru/d/shared", name="Another name", resource_type="dir", auto_run=False
            ),
            ctx=ctx,
        )

        assert response.reused is True
        repo.create.assert_not_called()
        ctx.session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disk_link_does_not_reuse_source_with_different_folder_filter(self, mocker):
        disk = mocker.patch("yandex_disk_module.client.YandexDiskClient").return_value
        disk.get_public_meta = AsyncMock(return_value={"type": "dir"})
        repo = mocker.patch("api.routers.recordings.InputSourceRepository").return_value
        repo.find_by_user = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=17,
                    source_type="YANDEX_DISK",
                    config={"public_url": "https://disk.yandex.ru/d/shared", "recursive": False},
                    is_active=True,
                )
            ]
        )
        repo.find_duplicate = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=SimpleNamespace(id=18))
        mocker.patch(
            "api.tasks.sync_tasks.sync_single_source_task.apply_async", return_value=SimpleNamespace(id="sync-18")
        )

        response = await add_public_disk_link(
            AddPublicDiskLinkRequest.model_construct(
                public_url="https://disk.yandex.ru/d/shared", name="All lectures", resource_type="dir", auto_run=False
            ),
            ctx=ServiceContext(session=AsyncMock(), user_id="user"),
        )

        assert response.reused is False
        assert response.source_id == 18
        assert repo.create.await_args.kwargs["config"]["recursive"] is True

    @pytest.mark.asyncio
    async def test_disk_preview_reports_file_or_folder_and_video_count(self, mocker):
        disk = mocker.patch("yandex_disk_module.client.YandexDiskClient").return_value
        disk.get_public_meta = AsyncMock(return_value={"type": "dir", "name": "Lectures"})
        disk.list_public_video_files = AsyncMock(return_value=[{"name": "a.mp4"}, {"name": "b.mkv"}])

        preview = await preview_public_disk_link(
            PublicDiskLinkRequest.model_construct(public_url="https://disk.yandex.ru/d/shared"),
            _ctx=ServiceContext(session=AsyncMock(), user_id="user"),
        )

        assert preview == {
            "resource_type": "dir",
            "name": "Lectures",
            "video_count": 2,
            "sample_names": ["a.mp4", "b.mkv"],
        }

    @pytest.mark.asyncio
    async def test_disk_add_rejects_kind_mismatch(self, mocker):
        disk = mocker.patch("yandex_disk_module.client.YandexDiskClient").return_value
        disk.get_public_meta = AsyncMock(return_value={"type": "dir"})
        repo = mocker.patch("api.routers.recordings.InputSourceRepository").return_value

        with pytest.raises(HTTPException) as error:
            await add_public_disk_link(
                AddPublicDiskLinkRequest.model_construct(
                    public_url="https://disk.yandex.ru/d/shared", name="Lecture", resource_type="file", auto_run=False
                ),
                ctx=ServiceContext(session=AsyncMock(), user_id="user"),
            )

        assert error.value.status_code == 422
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_playlist_preview_reports_skipped_videos(self, mocker):
        mocker.patch(
            "video_download_module.platforms.ytdlp.metadata.extract_playlist_entries",
            new=AsyncMock(return_value=[{"title": "Lecture 1"}, {"unavailable": True}]),
        )
        preview = await preview_playlist(
            FormatsPreviewRequest.model_construct(url="https://www.youtube.com/playlist?list=PL123"),
            _ctx=ServiceContext(session=AsyncMock(), user_id="user"),
        )
        assert preview == {"video_count": 1, "unavailable_count": 1, "sample_titles": ["Lecture 1"]}

    @pytest.mark.asyncio
    async def test_playlist_reimport_uses_stable_video_identity(self, mocker):
        quota = mocker.patch("api.routers.recordings.QuotaService").return_value
        quota.remaining_recordings_quota = AsyncMock(return_value=None)
        mocker.patch(
            "video_download_module.platforms.ytdlp.metadata.extract_playlist_entries",
            new=AsyncMock(
                return_value=[
                    {"id": "abc", "title": "Lecture", "url": "https://youtu.be/abc"},
                    {"unavailable": True},
                ]
            ),
        )
        repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
        repo.create_or_update = AsyncMock(return_value=(SimpleNamespace(id=42, display_name="Lecture"), False))
        config = mocker.patch("api.routers.recordings.UserConfigRepository").return_value
        config.get_effective_config = AsyncMock(return_value={})
        ctx = ServiceContext(session=AsyncMock(), user_id="user")

        result = await add_playlist_by_url(
            AddPlaylistByUrlRequest.model_construct(url="https://youtube.com/playlist?list=abc"),
            ctx=ctx,
            _quota=None,
        )

        assert result.recordings_created == 0
        assert result.recordings_updated == 1
        assert result.recordings_failed == 1
        assert result.total_videos == 2
        assert repo.create_or_update.await_args.kwargs["require_start_time_in_lookup"] is False

    @pytest.mark.asyncio
    async def test_playlist_import_respects_remaining_recording_quota(self, mocker):
        quota = mocker.patch("api.routers.recordings.QuotaService").return_value
        quota.remaining_recordings_quota = AsyncMock(return_value=1)
        mocker.patch(
            "video_download_module.platforms.ytdlp.metadata.extract_playlist_entries",
            new=AsyncMock(
                return_value=[
                    {"id": "new", "title": "New", "url": "https://youtu.be/new"},
                    {"id": "old", "title": "Old", "url": "https://youtu.be/old"},
                    {"id": "extra", "title": "Extra", "url": "https://youtu.be/extra"},
                ]
            ),
        )
        repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
        repo.create_or_update = AsyncMock(
            side_effect=[
                (SimpleNamespace(id=1, display_name="New"), True),
                (SimpleNamespace(id=2, display_name="Old"), False),
            ]
        )
        repo.find_by_source_key = AsyncMock(side_effect=[SimpleNamespace(id=2), None])
        config = mocker.patch("api.routers.recordings.UserConfigRepository").return_value
        config.get_effective_config = AsyncMock(return_value={})
        mocker.patch("api.routers.recordings._track_recordings_created", new=AsyncMock())
        ctx = ServiceContext(session=AsyncMock(), user_id="user")

        result = await add_playlist_by_url(
            AddPlaylistByUrlRequest.model_construct(url="https://youtube.com/playlist?list=abc"),
            ctx=ctx,
            _quota=None,
        )

        assert (result.recordings_created, result.recordings_updated, result.recordings_failed) == (1, 1, 1)
        assert repo.create_or_update.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("existing_name", "expected_name"),
        [("Original title", "Updated title"), ("My custom name", "My custom name")],
    )
    async def test_external_url_reimport_preserves_identity_and_custom_name(self, mocker, existing_name, expected_name):
        original_start = datetime(2025, 1, 1, tzinfo=UTC)
        recording = SimpleNamespace(
            id=42,
            deleted=False,
            status=ProcessingStatus.INITIALIZED,
            start_time=original_start,
            display_name=existing_name,
            duration=10,
            is_mapped=True,
            template_id=9,
            video_file_size=None,
            source=SimpleNamespace(source_key="youtube:abc", meta={"title": "Original title"}),
        )
        session = AsyncMock()
        repo = RecordingRepository(session)
        mocker.patch.object(repo, "find_by_source_key", new=AsyncMock(return_value=recording))

        result, is_new = await repo.create_or_update(
            user_id="user",
            input_source_id=None,
            display_name="Updated title",
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            duration=0,
            source_type=SourceType.EXTERNAL_URL,
            source_key="youtube:abc",
            source_metadata={"title": "Updated title"},
            is_mapped=False,
            template_id=None,
            require_start_time_in_lookup=False,
        )

        assert result is recording
        assert is_new is False
        assert recording.start_time == original_start
        assert recording.display_name == expected_name
        assert recording.duration == 10
        assert recording.is_mapped is True
        assert recording.template_id == 9
        assert recording.source.meta["title"] == "Updated title"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_source_auto_run_only_queues_each_new_recording_once(mocker):
    queue = mocker.patch("api.routers.recordings._auto_run_recording", new=AsyncMock(return_value="task"))

    started = await _queue_new_recordings([11, 11, 12], "user")

    assert started == 2
    assert [call.args for call in queue.await_args_list] == [(11, "user"), (12, "user")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_sync_queues_new_recordings_after_commit(mocker):
    session = AsyncMock()
    session_maker = MagicMock()
    session_maker.return_value.__aenter__ = AsyncMock(return_value=session)
    session_maker.return_value.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("api.tasks.sync_tasks.get_async_session_maker", return_value=session_maker)
    repo = mocker.patch("api.tasks.sync_tasks.InputSourceRepository").return_value
    repo.find_by_id = AsyncMock(return_value=SimpleNamespace(name="Disk folder"))
    mocker.patch(
        "api.routers.input_sources._sync_single_source",
        new=AsyncMock(
            return_value={
                "status": "success",
                "new_recording_ids": [11],
                "recordings_found": 1,
                "recordings_saved": 1,
                "recordings_updated": 0,
            }
        ),
    )

    async def queue_after_commit(_ids, _user_id):
        assert session.commit.await_count == 1
        return 1

    queue = mocker.patch("api.tasks.sync_tasks._queue_new_recordings", new=AsyncMock(side_effect=queue_after_commit))

    result = await _async_batch_sync_sources(MagicMock(), [7], "user", "2025-01-01", None, True)

    session.commit.assert_awaited_once()
    queue.assert_awaited_once_with([11], "user")
    assert result["pipelines_started"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reset_without_deletion_keeps_media_paths(mocker):
    recording = MagicMock()
    recording.id = 42
    recording.deleted = False
    recording.on_air = False
    recording.status = ProcessingStatus.PROCESSED
    recording.local_video_path = "source.mp4"
    recording.processed_video_path = "video.mp4"
    recording.processed_audio_path = "audio.mp3"
    recording.transcription_dir = "transcription/"
    recording.source.meta = {}
    repo = mocker.patch("api.routers.recordings.RecordingRepository").return_value
    repo.get_by_id = AsyncMock(return_value=recording)
    repo.sync_retention_deadline = AsyncMock()
    config = mocker.patch("api.routers.recordings.UserConfigRepository").return_value
    config.get_effective_config = AsyncMock(return_value={"retention": {}})
    ctx = ServiceContext(session=AsyncMock(), user_id="user")

    await reset_recording(42, delete_files=False, ctx=ctx)

    repo.sync_retention_deadline.assert_awaited_once_with(recording, {"retention": {}})
    assert recording.expire_at is None
    assert recording.local_video_path == "source.mp4"
    assert recording.processed_video_path == "video.mp4"
    assert recording.processed_audio_path == "audio.mp3"
    assert recording.transcription_dir == "transcription/"
    assert recording.status == ProcessingStatus.DOWNLOADED
