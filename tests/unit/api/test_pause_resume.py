"""Unit tests for pause/resume and smart run functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.recording import ProcessingStatus, TargetStatus, TargetType
from tests.fixtures.factories import create_mock_output_target, create_mock_recording

# =============================================================================
# Helper: status_manager.can_pause
# =============================================================================


@pytest.mark.unit
class TestCanPause:
    """Tests for can_pause helper function."""

    def test_can_pause_downloading(self):
        """DOWNLOADING status allows pausing."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.DOWNLOADING)
        assert can_pause(recording) is True

    def test_can_pause_processing(self):
        """PROCESSING status allows pausing."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSING)
        assert can_pause(recording) is True

    def test_can_pause_uploading(self):
        """UPLOADING status allows pausing."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.UPLOADING)
        assert can_pause(recording) is True

    def test_cannot_pause_ready(self):
        """READY is terminal, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.READY)
        assert can_pause(recording) is False

    def test_cannot_pause_uploaded(self):
        """UPLOADED is terminal, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.UPLOADED)
        assert can_pause(recording) is False

    def test_cannot_pause_skipped(self):
        """SKIPPED is terminal, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.SKIPPED)
        assert can_pause(recording) is False

    def test_cannot_pause_expired(self):
        """EXPIRED is terminal, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.EXPIRED)
        assert can_pause(recording) is False

    def test_cannot_pause_initialized(self):
        """INITIALIZED has not started, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.INITIALIZED)
        assert can_pause(recording) is False

    def test_cannot_pause_pending_source(self):
        """PENDING_SOURCE has not started, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PENDING_SOURCE)
        assert can_pause(recording) is False

    def test_cannot_pause_already_paused(self):
        """Already paused recording returns False."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSING, on_pause=True)
        assert can_pause(recording) is False

    def test_cannot_pause_downloaded(self):
        """DOWNLOADED has no active task, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.DOWNLOADED)
        assert can_pause(recording) is False

    def test_cannot_pause_processed(self):
        """PROCESSED has no active task, cannot pause."""
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSED)
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
            "api.services.config_utils.resolve_full_config",
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
            "api.services.config_utils.resolve_full_config",
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
            "api.services.config_utils.resolve_full_config",
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
            "api.services.config_utils.resolve_full_config",
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

    def _make(self, status, failed=False, on_pause=False):
        """Build a minimal mixin instance for testing."""
        from api.schemas.recording.response import PipelineControlMixin

        return PipelineControlMixin(
            status=status,
            failed=failed,
            on_pause=on_pause,
        )

    # is_runtime
    def test_is_runtime_downloading(self):
        """DOWNLOADING is a runtime status."""
        assert self._make(ProcessingStatus.DOWNLOADING).is_runtime is True

    def test_is_runtime_processing(self):
        """PROCESSING is a runtime status."""
        assert self._make(ProcessingStatus.PROCESSING).is_runtime is True

    def test_is_runtime_uploading(self):
        """UPLOADING is a runtime status."""
        assert self._make(ProcessingStatus.UPLOADING).is_runtime is True

    def test_is_runtime_ready_false(self):
        """READY is not a runtime status."""
        assert self._make(ProcessingStatus.READY).is_runtime is False

    def test_is_runtime_initialized_false(self):
        """INITIALIZED is not a runtime status."""
        assert self._make(ProcessingStatus.INITIALIZED).is_runtime is False

    # can_pause
    def test_can_pause_during_processing(self):
        """Can pause during PROCESSING."""
        assert self._make(ProcessingStatus.PROCESSING).can_pause is True

    def test_can_pause_false_when_ready(self):
        """Cannot pause when READY."""
        assert self._make(ProcessingStatus.READY).can_pause is False

    def test_can_pause_false_when_already_paused(self):
        """Cannot pause when already paused."""
        assert self._make(ProcessingStatus.PROCESSING, on_pause=True).can_pause is False

    def test_can_pause_false_when_initialized(self):
        """Cannot pause when INITIALIZED (not yet started)."""
        assert self._make(ProcessingStatus.INITIALIZED).can_pause is False

    # can_run
    def test_can_run_initialized(self):
        """Can run from INITIALIZED (start processing)."""
        assert self._make(ProcessingStatus.INITIALIZED).can_run is True

    def test_can_run_skipped(self):
        """Can run from SKIPPED (start with template)."""
        assert self._make(ProcessingStatus.SKIPPED).can_run is True

    def test_can_run_downloaded(self):
        """Can run from DOWNLOADED (continue to processing)."""
        assert self._make(ProcessingStatus.DOWNLOADED).can_run is True

    def test_can_run_when_paused_non_runtime(self):
        """Can run when on_pause is True and stage already completed (non-runtime)."""
        assert self._make(ProcessingStatus.DOWNLOADED, on_pause=True).can_run is True

    def test_cannot_run_while_pausing(self):
        """Cannot run while on_pause AND runtime (stage still completing)."""
        assert self._make(ProcessingStatus.PROCESSING, on_pause=True).can_run is False

    def test_cannot_run_while_pausing_downloading(self):
        """Cannot run while on_pause AND DOWNLOADING (download still in progress)."""
        assert self._make(ProcessingStatus.DOWNLOADING, on_pause=True).can_run is False

    def test_can_run_when_failed(self):
        """Can run when failed."""
        assert self._make(ProcessingStatus.DOWNLOADED, failed=True).can_run is True

    def test_cannot_run_ready(self):
        """Cannot run from READY (already complete)."""
        assert self._make(ProcessingStatus.READY).can_run is False

    def test_cannot_run_while_running(self):
        """Cannot run while actively running (not paused)."""
        assert self._make(ProcessingStatus.PROCESSING, on_pause=False).can_run is False

    def test_cannot_run_expired(self):
        """Cannot run from EXPIRED."""
        assert self._make(ProcessingStatus.EXPIRED).can_run is False

    def test_cannot_run_pending_source(self):
        """Cannot run from PENDING_SOURCE."""
        assert self._make(ProcessingStatus.PENDING_SOURCE).can_run is False

    def test_can_run_processed_paused(self):
        """Can run from PROCESSED + paused (pipeline stopped between stages)."""
        assert self._make(ProcessingStatus.PROCESSED, on_pause=True).can_run is True

    def test_can_run_uploaded_partial(self):
        """Can run from UPLOADED (partial uploads need to continue)."""
        assert self._make(ProcessingStatus.UPLOADED).can_run is True

    def test_can_run_processed(self):
        """Can run from PROCESSED (may have pending uploads)."""
        assert self._make(ProcessingStatus.PROCESSED).can_run is True


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

    def test_retry_upload_returns_404_or_405(self, client):
        """The /retry-upload endpoint should no longer exist."""
        response = client.post("/api/v1/recordings/1/retry-upload")
        # Should be 404 (path not found) or 405 (method not allowed)
        assert response.status_code in (404, 405, 422)
