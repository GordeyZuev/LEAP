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
    """Tests for can_pause helper function.

    can_pause now depends solely on on_air, not status.
    """

    def test_can_pause_when_on_air(self):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSING, on_air=True)
        assert can_pause(recording) is True

    def test_cannot_pause_when_not_on_air(self):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSING, on_air=False)
        assert can_pause(recording) is False

    @pytest.mark.parametrize("status", _RUNTIME)
    def test_cannot_pause_if_on_air_false_regardless_of_status(self, status):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=status, on_air=False)
        assert can_pause(recording) is False

    def test_cannot_pause_already_paused(self):
        from api.helpers.status_manager import can_pause

        recording = create_mock_recording(status=ProcessingStatus.PROCESSING, on_air=True, on_pause=True)
        assert can_pause(recording) is False


# =============================================================================
# Endpoint: POST /recordings/{id}/pause
# =============================================================================


@pytest.mark.unit
class TestPauseEndpoint:
    """Tests for POST /recordings/{id}/pause endpoint."""

    def test_pause_processing_recording(self, client, mocker):
        """Pause a recording that is actively processing (on_air=True)."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.PROCESSING,
            on_pause=False,
            on_air=True,
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
        assert "paused" in data["message"].lower()

    def test_pause_downloading_recording(self, client, mocker):
        """Pause a recording during download (on_air=True)."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.DOWNLOADING,
            on_pause=False,
            on_air=True,
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
            on_air=False,
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
        """Cannot pause a recording that is not on_air."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.READY,
            on_pause=False,
            on_air=False,
        )

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/pause")

        assert response.status_code == 409

    def test_pause_skipped_recording_fails(self, client, mocker):
        """Cannot pause a skipped recording (on_air=False)."""
        recording = create_mock_recording(
            record_id=1,
            status=ProcessingStatus.SKIPPED,
            on_pause=False,
            on_air=False,
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

    # --- on_air=True: reject (already running) ---

    def test_run_rejects_when_on_air(self, client, mocker):
        """on_air=True → 409 regardless of status."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADING, on_air=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409
        assert "active pipeline" in response.json()["detail"].lower()

    def test_run_rejects_active_processing(self, client, mocker):
        """on_air=True + PROCESSING → 409."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.PROCESSING, on_air=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409

    def test_run_rejects_active_uploading(self, client, mocker):
        """on_air=True + UPLOADING → 409."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.UPLOADING, on_air=True)

        mock_repo = mocker.patch("api.routers.recordings.RecordingRepository")
        mock_repo_instance = MagicMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=recording)
        mock_repo.return_value = mock_repo_instance

        response = client.post("/api/v1/recordings/1/run")

        assert response.status_code == 409

    # --- on_air=False + on_pause=True: resume (stable status after hard pause) ---

    def test_run_resumes_after_pause_downloading_status(self, client, mocker):
        """After hard pause from DOWNLOADING, status=INITIALIZED, on_pause=True, on_air=False → starts pipeline."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.INITIALIZED, on_pause=True, on_air=False)

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
        data = response.json()
        assert data["success"] is True
        mock_run.delay.assert_called_once()
        assert recording.on_pause is False

    def test_run_resumes_after_pause_processing_status(self, client, mocker):
        """After hard pause from PROCESSING, status=DOWNLOADED, on_pause=True, on_air=False → starts pipeline."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADED, on_pause=True, on_air=False)

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
        data = response.json()
        assert data["success"] is True
        mock_run.delay.assert_called_once()
        assert recording.on_pause is False

    # --- Non-runtime paused: clear on_pause flag and launch new pipeline ---

    def test_run_clears_pause_and_continues(self, client, mocker):
        """DOWNLOADED + paused (on_air=False) → clears pause flag, starts new pipeline."""
        recording = create_mock_recording(record_id=1, status=ProcessingStatus.DOWNLOADED, on_pause=True, on_air=False)

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

        # Mock celery.chain used in PROCESSED/UPLOADED dispatch path
        mock_chain_result = MagicMock()
        mock_chain_result.id = "up-task-1"
        mock_celery_chain = mocker.patch("celery.chain")
        mock_celery_chain.return_value.apply_async.return_value = mock_chain_result

        mocker.patch("api.tasks.processing._launch_uploads_task")
        mocker.patch("api.tasks.processing._finalize_pipeline_task")

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

        # Mock celery.chain used in PROCESSED/UPLOADED dispatch path
        mock_chain_result = MagicMock()
        mock_chain_result.id = "up-task-2"
        mock_celery_chain = mocker.patch("celery.chain")
        mock_celery_chain.return_value.apply_async.return_value = mock_chain_result

        mocker.patch("api.tasks.processing._launch_uploads_task")
        mocker.patch("api.tasks.processing._finalize_pipeline_task")

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
    def _make(status, failed=False, on_pause=False, on_air=False):
        from api.schemas.recording.response import PipelineControlMixin

        return PipelineControlMixin(
            status=status,
            failed=failed,
            on_pause=on_pause,
            on_air=on_air,
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

    def test_can_pause_true_when_on_air(self):
        assert self._make(ProcessingStatus.DOWNLOADING, on_air=True).can_pause is True

    def test_can_pause_false_when_not_on_air(self):
        assert self._make(ProcessingStatus.DOWNLOADING, on_air=False).can_pause is False

    def test_can_pause_false_when_on_air_but_already_paused(self):
        assert self._make(ProcessingStatus.PROCESSING, on_air=True, on_pause=True).can_pause is False

    @pytest.mark.parametrize(
        "status,failed,on_pause,on_air,expected",
        [
            # Stable statuses with on_air=False → can run
            (ProcessingStatus.INITIALIZED, False, False, False, True),
            (ProcessingStatus.SKIPPED, False, False, False, True),
            (ProcessingStatus.DOWNLOADED, False, False, False, True),
            (ProcessingStatus.PROCESSED, False, False, False, True),
            (ProcessingStatus.UPLOADED, False, False, False, True),
            # After hard pause: stable status + on_pause=True + on_air=False → can run (resume)
            (ProcessingStatus.DOWNLOADED, False, True, False, True),
            (ProcessingStatus.INITIALIZED, False, True, False, True),
            # Failed → can run
            (ProcessingStatus.DOWNLOADED, True, False, False, True),
            # on_air=True → cannot run (pipeline active)
            (ProcessingStatus.DOWNLOADING, False, False, True, False),
            (ProcessingStatus.PROCESSING, False, False, True, False),
            (ProcessingStatus.UPLOADING, False, False, True, False),
            # Terminal statuses → cannot run
            (ProcessingStatus.READY, False, False, False, False),
            (ProcessingStatus.EXPIRED, False, False, False, False),
            (ProcessingStatus.PENDING_SOURCE, False, False, False, False),
        ],
    )
    def test_can_run(self, status, failed, on_pause, on_air, expected):
        assert self._make(status, failed=failed, on_pause=on_pause, on_air=on_air).can_run is expected


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
