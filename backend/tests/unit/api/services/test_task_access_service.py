"""Celery task ownership binding and fail-closed access checks."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.services.task_access_service import TaskAccessService
from api.tasks.base import extract_task_owner_user_id


@pytest.mark.unit
class TestExtractTaskOwnerUserId:
    def test_prefers_kwargs(self):
        assert extract_task_owner_user_id((1, "other"), {"user_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}) == (
            "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        )

    def test_second_positional_ulid(self):
        assert extract_task_owner_user_id((42, "01ARZ3NDEKTSV4RRFFQ69G5FAV"), None) == "01ARZ3NDEKTSV4RRFFQ69G5FAV"

    def test_missing(self):
        assert extract_task_owner_user_id((42,), {}) is None
        assert extract_task_owner_user_id(None, None) is None


@pytest.mark.unit
class TestTaskAccessService:
    def test_redis_owner_match_allows(self, mocker):
        task = MagicMock()
        task.state = "PENDING"
        mocker.patch("api.services.task_access_service.lookup_task_owner", return_value="user_a")
        mocker.patch("api.services.task_access_service.AsyncResult", return_value=task)

        assert TaskAccessService.validate_task_access("tid", "user_a") is task

    def test_redis_owner_mismatch_forbidden(self, mocker):
        task = MagicMock()
        task.state = "PENDING"
        mocker.patch("api.services.task_access_service.lookup_task_owner", return_value="user_b")
        mocker.patch("api.services.task_access_service.AsyncResult", return_value=task)

        with pytest.raises(HTTPException) as exc:
            TaskAccessService.validate_task_access("tid", "user_a")
        assert exc.value.status_code == 403

    def test_pending_without_owner_is_forbidden(self, mocker):
        task = MagicMock()
        task.state = "PENDING"
        task.info = None
        mocker.patch("api.services.task_access_service.lookup_task_owner", return_value=None)
        mocker.patch("api.services.task_access_service.AsyncResult", return_value=task)

        with pytest.raises(HTTPException) as exc:
            TaskAccessService.validate_task_access("tid", "user_a")
        assert exc.value.status_code == 403

    def test_success_meta_owner_allows(self, mocker):
        task = MagicMock()
        task.state = "SUCCESS"
        task.info = {"user_id": "user_a"}
        task.result = {"user_id": "user_a"}
        mocker.patch("api.services.task_access_service.lookup_task_owner", return_value=None)
        mocker.patch("api.services.task_access_service.AsyncResult", return_value=task)

        assert TaskAccessService.validate_task_access("tid", "user_a") is task
