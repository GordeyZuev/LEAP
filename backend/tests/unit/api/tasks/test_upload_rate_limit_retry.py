"""Celery retry policy for upload_recording_to_platform on provider rate limits."""

import pytest
from celery.exceptions import Retry

from api.shared.exceptions import CredentialError, ExternalRateLimitError
from api.tasks.upload import upload_recording_to_platform


@pytest.mark.unit
def test_upload_retries_rate_limit_with_short_countdown(mocker) -> None:
    exc = ExternalRateLimitError(platform="vk_video", retry_after=1.0, credential_id=17)

    async def fail(*_args, **_kwargs):
        raise exc

    mocker.patch("api.tasks.upload._async_upload_recording", new=fail)
    mocker.patch("api.tasks.upload.rate_limit_countdown", return_value=2.5)
    retry_mock = mocker.patch.object(upload_recording_to_platform, "retry", side_effect=Retry())

    with pytest.raises(Retry):
        upload_recording_to_platform.run(132, "user-01", "vk")

    retry_mock.assert_called_once_with(countdown=2.5, exc=exc)


@pytest.mark.unit
def test_upload_credential_error_is_not_retried(mocker) -> None:
    exc = CredentialError(platform="vk", reason="Token validation failed")

    async def fail(*_args, **_kwargs):
        raise exc

    mocker.patch("api.tasks.upload._async_upload_recording", new=fail)
    retry_mock = mocker.patch.object(upload_recording_to_platform, "retry", side_effect=Retry())
    build = mocker.patch.object(
        upload_recording_to_platform,
        "build_result",
        return_value={"status": "failed"},
    )

    result = upload_recording_to_platform.run(132, "user-01", "vk")

    retry_mock.assert_not_called()
    build.assert_called_once()
    assert result["status"] == "failed"
