"""Celery retry policy for download_recording_task on provider rate limits."""

import pytest
from celery.exceptions import Retry

from api.shared.exceptions import ExternalRateLimitError
from api.tasks.processing import download_recording_task


@pytest.mark.unit
def test_download_retries_rate_limit_with_short_countdown(mocker) -> None:
    exc = ExternalRateLimitError(platform="mts_link", retry_after=1.0, credential_id=42)
    mocker.patch("api.tasks.processing._run_download_recording", side_effect=exc)
    mocker.patch.object(download_recording_task, "update_progress")
    mocker.patch("api.tasks.processing.rate_limit_countdown", return_value=2.5)
    retry_mock = mocker.patch.object(download_recording_task, "retry", side_effect=Retry())

    with pytest.raises(Retry):
        download_recording_task.run(132, "user-01", False, None)

    retry_mock.assert_called_once_with(countdown=2.5, exc=exc)


@pytest.mark.unit
def test_download_other_errors_use_default_retry(mocker) -> None:
    exc = RuntimeError("cdn timeout")
    mocker.patch("api.tasks.processing._run_download_recording", side_effect=exc)
    mocker.patch.object(download_recording_task, "update_progress")
    retry_mock = mocker.patch.object(download_recording_task, "retry", side_effect=Retry())

    with pytest.raises(Retry):
        download_recording_task.run(132, "user-01", False, None)

    retry_mock.assert_called_once_with(exc=exc)
