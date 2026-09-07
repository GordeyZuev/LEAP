"""HTTP access-log and Celery postrun log-level mapping."""

import pytest

from api.celery_app import _postrun_log_level
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
