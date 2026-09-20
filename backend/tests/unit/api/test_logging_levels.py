"""HTTP access-log and Celery postrun log-level mapping."""

import pytest

from api.celery_app import _clear_enqueue_time, _postrun_log_level
from api.middleware.logging import _level_for_status


@pytest.mark.unit
class TestHttpAccessLogLevel:
    def test_success_is_info(self) -> None:
        assert _level_for_status(200) == "INFO"
        assert _level_for_status(204) == "INFO"
        assert _level_for_status(302) == "INFO"

    def test_mundane_client_errors_are_info(self) -> None:
        assert _level_for_status(400) == "INFO"
        assert _level_for_status(401) == "INFO"
        assert _level_for_status(404) == "INFO"
        assert _level_for_status(422) == "INFO"

    def test_actionable_client_errors_are_warning(self) -> None:
        assert _level_for_status(403) == "WARNING"
        assert _level_for_status(409) == "WARNING"
        assert _level_for_status(413) == "WARNING"
        assert _level_for_status(429) == "WARNING"

    def test_server_errors_are_error(self) -> None:
        assert _level_for_status(500) == "ERROR"
        assert _level_for_status(503) == "ERROR"


@pytest.mark.unit
class TestCeleryPostrunLogLevel:
    def test_success_and_ignored_are_info(self) -> None:
        assert _postrun_log_level("SUCCESS") == "INFO"
        assert _postrun_log_level("IGNORED") == "INFO"

    def test_retry_and_failure_defer_to_dedicated_handlers(self) -> None:
        assert _postrun_log_level("RETRY") == "DEBUG"
        assert _postrun_log_level("FAILURE") == "DEBUG"

    def test_unknown_state_is_warning(self) -> None:
        assert _postrun_log_level("REVOKED") == "WARNING"


@pytest.mark.unit
def test_celery_prerun_enqueue_cleanup_accepts_signal_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    class RedisStub:
        def __init__(self) -> None:
            self.removed: list[tuple[str, str]] = []

        def zrem(self, key: str, task_id: str) -> None:
            self.removed.append((key, task_id))

    redis_stub = RedisStub()
    monkeypatch.setattr("api.celery_app._publish_redis", lambda: redis_stub)

    _clear_enqueue_time(task_id="task-123", task=object(), sender=object())

    assert redis_stub.removed
    assert all(task_id == "task-123" for _, task_id in redis_stub.removed)
