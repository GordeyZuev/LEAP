"""Unit tests for the require_feature dependency factory."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_feature_allows_when_flag_true():
    from api.auth.dependencies import require_feature

    check = require_feature("can_upload")
    user = SimpleNamespace(can_upload=True)

    result = await check(current_user=user)
    assert result is user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_feature_blocks_when_flag_false():
    from api.auth.dependencies import require_feature

    check = require_feature("can_upload")
    user = SimpleNamespace(can_upload=False)

    with pytest.raises(HTTPException) as exc:
        await check(current_user=user)
    assert exc.value.status_code == 403
    assert "can_upload" in exc.value.detail


@pytest.mark.unit
def test_require_feature_unique_dependency_name():
    """Each factory call must produce a distinctly-named dependency for FastAPI."""
    from api.auth.dependencies import require_feature

    assert require_feature("can_upload").__name__ == "require_feature_can_upload"
    assert require_feature("can_transcribe").__name__ == "require_feature_can_transcribe"


@pytest.mark.unit
def test_require_feature_unknown_flag_raises_at_factory():
    """A typo'd flag must fail loudly at import/factory time, not silently allow."""
    from api.auth.dependencies import require_feature

    with pytest.raises(ValueError):
        require_feature("can_uploads")  # not a real flag


@pytest.mark.unit
def test_quota_exceeded_is_plain_exception_not_retry():
    """QuotaExceededError must be an ordinary Exception so the transcribe task can
    re-raise it without triggering Celery retries."""
    from api.services.quota_service import QuotaExceededError

    assert issubclass(QuotaExceededError, Exception)
    err = QuotaExceededError("limit")
    assert str(err) == "limit"
