"""Unit tests for pause/resume and smart run functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.recording import ProcessingStatus, TargetStatus, TargetType
from tests.fixtures.factories import create_mock_output_target, create_mock_recording

# =============================================================================
# Helper: status_manager.can_pause
# =============================================================================


_RUNTIME = (
    ProcessingStatus.DOWNLOADING,
    ProcessingStatus.PROCESSING,
    ProcessingStatus.UPLOADING,
)


@pytest.mark.unit
class TestCanPause:
    """Tests for can_pause helper function."""

    @pytest.mark.parametrize("status", _RUNTIME)
    def test_can_pause_while_runtime(self, status):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=status)
        assert can_pause(recording) is True

    @pytest.mark.parametrize(
        "status",
        tuple(s for s in ProcessingStatus if s not in _RUNTIME),
    )
    def test_cannot_pause_when_not_runtime(self, status):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=status)
        assert can_pause(recording) is False

    def test_cannot_pause_already_paused(self):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSING, on_pause=True)
        assert can_pause(recording) is False


# =============================================================================
# Endpoint: POST /recordings/{id}/pause
# =============================================================================


@pytest.mark.unit
class TestPauseEndpoint:
    """Tests for POST /recordings/{id}/pause endpoint."""

    def test_pause_processing_recording(self, client, mocker):
        """Pause a recording that is actively processing."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.PROCESSING,
            on_pause=False,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["on_pause"] is True
        assert "current stage will complete" in data["message"].lower()

    def test_pause_downloading_recording(self, client, mocker):
        """Pause a recording during download."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.DOWNLOADING,
            on_pause=False,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["on_pause"] is True

    def test_pause_already_paused_is_idempotent(self, client, mocker):
        """Pausing an already-paused recording returns success without error."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.PROCESSING,
            on_pause=True,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "already paused" in data["message"].lower()

    def test_pause_ready_recording_fails(self, client, mocker):
        """Cannot pause a completed recording."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.READY,
            on_pause=False,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/pause")

        assert response.status_code == 409

    def test_pause_skipped_recording_fails(self, client, mocker):
        """Cannot pause a skipped recording."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.SKIPPED,
            on_pause=False,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/pause")

        assert response.status_code == 409

    def test_pause_not_found(self, client, mocker):
        """Pause returns 404 for non-existent recording."""
        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/999/pause")

        assert response.status_code == 404


# =============================================================================
# Endpoint: POST /recordings/{id}/run (unified smart run)
# =============================================================================


@pytest.mark.unit
class TestSmartRun:
    """Tests for unified smart /run endpoint (no resume param)."""

    # --- Fresh start statuses ---

    def test_run_initialized_starts_pipeline(self, client, mocker):
        """INITIALIZED → starts full pipeline."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.INITIALIZED)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {"auto_upload": False}, recording),
        )

        mock_task = mocker.patch("api.tasks.processing.run_recording_task")
        mock_task.delay = MagicMock(return_value=MagicMock(id="task-123"))

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == "task-123"
        mock_task.delay.assert_called_once()

    def test_run_skipped_starts_pipeline(self, client, mocker):
        """SKIPPED → starts full pipeline."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.SKIPPED)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {"auto_upload": False}, recording),
        )

        mock_task = mocker.patch("api.tasks.processing.run_recording_task")
        mock_task.delay = MagicMock(return_value=MagicMock(id="task-123"))

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_task.delay.assert_called_once()

    def test_run_downloaded_starts_processing(self, client, mocker):
        """DOWNLOADED → starts processing (skip download)."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADED)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {"auto_upload": False}, recording),
        )

        mock_task = mocker.patch("api.tasks.processing.run_recording_task")
        mock_task.delay = MagicMock(return_value=MagicMock(id="task-456"))

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "download" in data["message"].lower()
        mock_task.delay.assert_called_once()

    # --- Runtime statuses: reject if not paused ---

    def test_run_rejects_active_downloading(self, client, mocker):
        """DOWNLOADING + not paused → 409 already running."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADING, on_pause=False)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409
        assert "already being processed" in response.json()["detail"].lower()

    def test_run_rejects_active_processing(self, client, mocker):
        """PROCESSING + not paused → 409 already running."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.PROCESSING, on_pause=False)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409

    def test_run_rejects_active_uploading(self, client, mocker):
        """UPLOADING + not paused → 409 already running."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.UPLOADING, on_pause=False)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409

    # --- Runtime + paused: clear pause flag ---

    def test_run_unpauses_downloading(self, client, mocker):
        """DOWNLOADING + paused → clears flag, no new task."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADING, on_pause=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mock_download = mocker.patch("api.tasks.processing.download_recording_task")
        mock_run = mocker.patch("api.tasks.processing.run_recording_task")

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "continue" in data["message"].lower()
        assert data.get("task_id") is None
        mock_download.delay.assert_not_called()
        mock_run.delay.assert_not_called()
        assert recording.on_pause is False

    def test_run_unpauses_uploading(self, client, mocker):
        """UPLOADING + paused → clears flag, no new task."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.UPLOADING, on_pause=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mock_upload = mocker.patch("api.tasks.upload.upload_recording_to_platform")

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "continue" in data["message"].lower()
        assert data.get("task_id") is None
        mock_upload.delay.assert_not_called()
        assert recording.on_pause is False

    def test_run_unpauses_processing(self, client, mocker):
        """PROCESSING + paused → clears flag, no new task."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.PROCESSING, on_pause=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mock_run = mocker.patch("api.tasks.processing.run_recording_task")

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data.get("task_id") is None
        mock_run.delay.assert_not_called()
        assert recording.on_pause is False

    # --- Non-runtime paused: clear flag and resume ---

    def test_run_clears_pause_and_continues(self, client, mocker):
        """DOWNLOADED + paused → clears pause flag, starts processing."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADED, on_pause=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {"auto_upload": False}, recording),
        )

        mock_run = mocker.patch("api.tasks.processing.run_recording_task")
        mock_run.delay = MagicMock(return_value=MagicMock(id="run-task-1"))

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        assert recording.on_pause is False
        assert recording.pause_requested_at is None
        mock_run.delay.assert_called_once()

    # --- Upload retry statuses ---

    def test_run_processed_retries_failed_uploads(self, client, mocker):
        """PROCESSED + failed uploads → retries uploads."""
        failed_output = create_mock_output_target(
            target_type=TargetType.YOUTUBE,
            status=TargetStatus.FAILED,
            preset_id=10,
        )
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.PROCESSED,
            outputs=[failed_output],
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        # Mock resolve_full_config — called for PROCESSED/UPLOADED statuses
        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {}, recording),
        )

        mock_upload = mocker.patch("api.tasks.upload.upload_recording_to_platform")
        mock_upload.delay = MagicMock(return_value=MagicMock(id="up-task-1"))

        # Mock _launch_uploads_task used by the run endpoint (local import from api.tasks.processing)
        mock_launch = mocker.patch("api.tasks.processing._launch_uploads_task")
        mock_launch.delay = MagicMock(return_value=MagicMock(id="up-task-1"))

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "upload" in data["message"].lower()

    def test_run_uploaded_retries_pending(self, client, mocker):
        """UPLOADED + pending uploads → retries pending."""
        uploaded = create_mock_output_target(
            target_id=1,
            target_type=TargetType.YOUTUBE,
            status=TargetStatus.UPLOADED,
        )
        pending = create_mock_output_target(
            target_id=2,
            target_type=TargetType.VK,
            status=TargetStatus.NOT_UPLOADED,
            preset_id=5,
        )
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.UPLOADED,
            outputs=[uploaded, pending],
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        # Mock resolve_full_config — called for PROCESSED/UPLOADED statuses
        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {}, recording),
        )

        # Mock _launch_uploads_task used by the run endpoint (local import from api.tasks.processing)
        mock_launch = mocker.patch("api.tasks.processing._launch_uploads_task")
        mock_launch.delay = MagicMock(return_value=MagicMock(id="up-task-2"))

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "1" in data["message"] and "upload" in data["message"].lower()

    def test_run_processed_no_outputs_returns_complete(self, client, mocker):
        """PROCESSED + no outputs → returns 'complete'."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.PROCESSED,
            outputs=[],
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        # Mock resolve_full_config — called for PROCESSED/UPLOADED statuses
        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {}, recording),
        )

        mock_run = mocker.patch("api.tasks.processing.run_recording_task")

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "no pending" in data["message"].lower()
        mock_run.delay.assert_not_called()

    def test_run_processed_all_uploaded_returns_complete(self, client, mocker):
        """PROCESSED + all outputs uploaded → returns 'complete'."""
        uploaded_output = create_mock_output_target(
            target_type=TargetType.YOUTUBE,
            status=TargetStatus.UPLOADED,
        )
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.PROCESSED,
            outputs=[uploaded_output],
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        # Mock resolve_full_config — called for PROCESSED/UPLOADED statuses
        mocker.patch(
            "api.routers.recordings.resolve_full_config",
            new_callable=AsyncMock,
            return_value=({}, {}, recording),
        )

        mock_run = mocker.patch("api.tasks.processing.run_recording_task")

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert "no pending" in data["message"].lower()
        mock_run.delay.assert_not_called()

    # --- Terminal/complete statuses ---

    def test_run_ready_returns_complete(self, client, mocker):
        """READY → returns 'already complete'."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.READY)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "already complete" in data["message"].lower()

    def test_run_expired_returns_409(self, client, mocker):
        """EXPIRED → 409 cannot run."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.EXPIRED)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409

    def test_run_pending_source_returns_409(self, client, mocker):
        """PENDING_SOURCE → 409 cannot run."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.PENDING_SOURCE)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409

    # --- Not found ---

    def test_run_not_found(self, client, mocker):
        """Non-existent recording → 404."""
        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/999/run")

        assert response.status_code == 404


# =============================================================================
# Pydantic: PipelineControlMixin computed fields
# =============================================================================


@pytest.mark.unit
class TestPipelineControlComputedFields:
    """Tests for is_runtime, can_pause, can_run computed fields."""

    @staticmethod
    def _make(status, failed=False, on_pause=False):
        from api.schemas.recording.response import PipelineControlMixin

        return PipelineControlMixin(
            status=status,
            failed=failed,
            on_pause=on_pause,
        )

    @pytest.mark.parametrize("status", _RUNTIME)
    def test_is_runtime_true(self, status):
        assert self._make(status).is_runtime is True

    @pytest.mark.parametrize(
        "status",
        tuple(s for s in ProcessingStatus if s not in _RUNTIME),
    )
    def test_is_runtime_false(self, status):
        assert self._make(status).is_runtime is False

    @pytest.mark.parametrize("status", _RUNTIME)
    def test_can_pause_true_when_not_on_pause(self, status):
        assert self._make(status).can_pause is True

    @pytest.mark.parametrize(
        "status",
        tuple(s for s in ProcessingStatus if s not in _RUNTIME),
    )
    def test_can_pause_false_when_not_runtime(self, status):
        assert self._make(status).can_pause is False

    def test_can_pause_false_when_already_paused(self):
        assert self._make(ProcessingStatus.PROCESSING, on_pause=True).can_pause is False

    @pytest.mark.parametrize(
        "status,failed,on_pause,expected",
        [
            (ProcessingStatus.INITIALIZED, False, False, True),
            (ProcessingStatus.SKIPPED, False, False, True),
            (ProcessingStatus.DOWNLOADED, False, False, True),
            (ProcessingStatus.DOWNLOADED, False, True, True),
            (ProcessingStatus.PROCESSING, False, True, False),
            (ProcessingStatus.DOWNLOADING, False, True, False),
            (ProcessingStatus.DOWNLOADED, True, False, True),
            (ProcessingStatus.READY, False, False, False),
            (ProcessingStatus.PROCESSING, False, False, False),
            (ProcessingStatus.EXPIRED, False, False, False),
            (ProcessingStatus.PENDING_SOURCE, False, False, False),
            (ProcessingStatus.PROCESSED, False, True, True),
            (ProcessingStatus.UPLOADED, False, False, True),
            (ProcessingStatus.PROCESSED, False, False, True),
        ],
    )
    def test_can_run(self, status, failed, on_pause, expected):
        assert self._make(status, failed=failed, on_pause=on_pause).can_run is expected


# =============================================================================
# Pydantic: PauseRecordingResponse schema validation
# =============================================================================


@pytest.mark.unit
class TestPauseRecordingResponse:
    """Tests for PauseRecordingResponse schema."""

    def test_valid_response(self):
        from api.schemas.recording.operations import PauseRecordingResponse

        resp = PauseRecordingResponse(
            success=True,
            recording_id=1,
            message="Paused",
            status=ProcessingStatus.PROCESSING,
            on_pause=True,
        )
        assert resp.success is True
        assert resp.on_pause is True
        assert resp.status == ProcessingStatus.PROCESSING


# =============================================================================
# Endpoint: retry-upload removed
# =============================================================================


@pytest.mark.unit
class TestRetryUploadRemoved:
    """Verify /retry-upload endpoint is removed."""

    def test_retry_upload_route_removed(self, client):
        """The /retry-upload path must not be served (no 2xx / validation on a live handler)."""
        response = client.post("/api/v1/recordings/1/retry-upload")
        assert response.status_code in (404, 405)
