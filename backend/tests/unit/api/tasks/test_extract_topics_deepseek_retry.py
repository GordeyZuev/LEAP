"""Celery retry policy for extract_topics_task on DeepSeek errors."""

import pytest
from celery.exceptions import Retry

from api.tasks.processing import extract_topics_task
from config.settings import get_settings
from deepseek_module import DeepSeekError

settings = get_settings()


def _run_async_raises(exc: DeepSeekError):
    def _inner(coro):
        coro.close()
        raise exc

    return _inner


@pytest.mark.unit
def test_extract_topics_retries_transient_deepseek_with_delayed_countdown(mocker) -> None:
    exc = DeepSeekError(
        "DeepSeek API error: We were unable to start processing your request within the "
        "900-second timeout limit. Please try again later."
    )
    mocker.patch.object(extract_topics_task, "run_async", side_effect=_run_async_raises(exc))
    mocker.patch.object(extract_topics_task, "update_progress")
    retry_mock = mocker.patch.object(extract_topics_task, "retry", side_effect=Retry())

    with pytest.raises(Retry):
        extract_topics_task.run(132, "user-01", "long", None, False)

    retry_mock.assert_called_once_with(
        countdown=settings.celery.deepseek_transient_retry_delay,
        exc=exc,
    )


@pytest.mark.unit
def test_extract_topics_does_not_retry_non_transient_deepseek(mocker) -> None:
    exc = DeepSeekError("DeepSeek JSON parse failed: Expecting value")
    mocker.patch.object(extract_topics_task, "run_async", side_effect=_run_async_raises(exc))
    mocker.patch.object(extract_topics_task, "update_progress")
    retry_mock = mocker.patch.object(extract_topics_task, "retry", side_effect=AssertionError("retry should not run"))

    with pytest.raises(DeepSeekError):
        extract_topics_task.run(132, "user-01", "long", None, False)

    retry_mock.assert_not_called()
