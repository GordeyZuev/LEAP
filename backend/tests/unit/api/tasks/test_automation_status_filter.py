from types import SimpleNamespace

import pytest

from api.schemas.automation.filters import DEFAULT_AUTOMATION_STATUS_FILTER
from api.tasks.automation import _resolve_status_filter, _should_enqueue_recording
from models.recording import ProcessingStatus, SourceType


@pytest.mark.unit
def test_missing_status_key_uses_mts_aware_default():
    assert _resolve_status_filter({}) == list(DEFAULT_AUTOMATION_STATUS_FILTER)


@pytest.mark.unit
def test_empty_status_list_means_all():
    assert _resolve_status_filter({"status": []}) is None


@pytest.mark.unit
def test_legacy_invalid_statuses_are_dropped():
    assert _resolve_status_filter({"status": ["INITIALIZED", "FAILED", "TRANSCRIBED"]}) == ["INITIALIZED"]


@pytest.mark.unit
def test_garbage_only_status_list_falls_back_to_default():
    assert _resolve_status_filter({"status": ["FAILED"]}) == list(DEFAULT_AUTOMATION_STATUS_FILTER)


def _rec(*, status, on_air=False, on_pause=False, source_type=None, deleted=False):
    source = SimpleNamespace(source_type=source_type) if source_type is not None else None
    return SimpleNamespace(status=status, on_air=on_air, on_pause=on_pause, source=source, deleted=deleted)


@pytest.mark.unit
def test_enqueue_skips_on_air():
    rec = _rec(status=ProcessingStatus.INITIALIZED, on_air=True)
    assert _should_enqueue_recording(rec) is False


@pytest.mark.unit
def test_enqueue_skips_paused():
    rec = _rec(status=ProcessingStatus.INITIALIZED, on_pause=True)
    assert _should_enqueue_recording(rec) is False


@pytest.mark.unit
def test_enqueue_skips_zoom_pending_source():
    rec = _rec(status=ProcessingStatus.PENDING_SOURCE, source_type=SourceType.ZOOM)
    assert _should_enqueue_recording(rec) is False


@pytest.mark.unit
def test_enqueue_allows_mts_pending_source():
    rec = _rec(status=ProcessingStatus.PENDING_SOURCE, source_type=SourceType.MTS_LINK)
    assert _should_enqueue_recording(rec) is True


@pytest.mark.unit
def test_enqueue_allows_initialized():
    rec = _rec(status=ProcessingStatus.INITIALIZED, source_type=SourceType.ZOOM)
    assert _should_enqueue_recording(rec) is True


@pytest.mark.unit
def test_enqueue_skips_expired_and_deleted():
    assert _should_enqueue_recording(_rec(status=ProcessingStatus.EXPIRED)) is False
    assert _should_enqueue_recording(_rec(status=ProcessingStatus.INITIALIZED, deleted=True)) is False
