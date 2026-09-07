import pytest

from api.helpers.blank_record import (
    MTS_LINK_BLANK_MIN_DURATION_SECONDS,
    apply_blank_record,
    is_blank_recording,
    is_mts_link_blank,
    mts_link_record_id_from_source_key,
    positive_duration_seconds,
)
from models.recording import ProcessingStatus
from tests.fixtures.factories import create_mock_recording


@pytest.mark.unit
class TestPositiveDuration:
    def test_parses_int_and_float(self):
        assert positive_duration_seconds(39) == 39.0
        assert positive_duration_seconds(6058.8) == pytest.approx(6058.8)

    def test_rejects_missing_and_non_positive(self):
        assert positive_duration_seconds(None) is None
        assert positive_duration_seconds(0) is None
        assert positive_duration_seconds(-1) is None
        assert positive_duration_seconds("x") is None


@pytest.mark.unit
class TestBlankHeuristics:
    def test_zoom_short_or_small(self):
        assert is_blank_recording(39, 80 * 1024 * 1024) is True
        assert is_blank_recording(3600, 1024) is True
        assert is_blank_recording(3600, 80 * 1024 * 1024) is False

    def test_incomplete_never_blank(self):
        assert is_blank_recording(10, 0, source_processing_incomplete=True) is False

    def test_mts_duration_only(self):
        assert is_mts_link_blank(None) is False
        assert is_mts_link_blank(4) is True
        assert is_mts_link_blank(39) is True
        assert is_mts_link_blank(599) is True
        assert is_mts_link_blank(600) is False
        assert is_mts_link_blank(1055) is False
        assert MTS_LINK_BLANK_MIN_DURATION_SECONDS == 600

    def test_any_known_short_duration_is_blank(self):
        from api.helpers.blank_record import is_mts_link_blank_any

        assert is_mts_link_blank_any(6058, 4) is True
        assert is_mts_link_blank_any(6058, None) is False
        assert is_mts_link_blank_any(None, 39) is True


@pytest.mark.unit
class TestPreserveMtsDuration:
    def test_keeps_duration_once_media_is_downloaded(self):
        from api.helpers.blank_record import preserve_mts_recording_duration

        assert preserve_mts_recording_duration(has_downloaded_media=True, existing_duration=6058) is True
        assert preserve_mts_recording_duration(has_downloaded_media=True, existing_duration=4) is True

    def test_keeps_short_duration_even_without_path(self):
        from api.helpers.blank_record import preserve_mts_recording_duration

        assert preserve_mts_recording_duration(has_downloaded_media=False, existing_duration=4) is True
        assert preserve_mts_recording_duration(has_downloaded_media=False, existing_duration=6058) is False
        assert preserve_mts_recording_duration(has_downloaded_media=False, existing_duration=0) is False


@pytest.mark.unit
class TestMtsSourceKey:
    def test_parses_record_id(self):
        assert mts_link_record_id_from_source_key("mtslink:record:2047846301") == 2047846301
        assert mts_link_record_id_from_source_key("zoom:abc") is None


@pytest.mark.unit
class TestApplyBlankRecord:
    def test_initialized_becomes_skipped(self):
        rec = create_mock_recording()
        rec.status = ProcessingStatus.INITIALIZED
        rec.on_air = False
        apply_blank_record(rec, True, reason="Blank record (too short or too small)")
        assert rec.blank_record is True
        assert rec.status == ProcessingStatus.SKIPPED

    def test_uploaded_keeps_status(self):
        rec = create_mock_recording()
        rec.status = ProcessingStatus.UPLOADED
        rec.on_air = False
        apply_blank_record(rec, True, reason="x")
        assert rec.blank_record is True
        assert rec.status == ProcessingStatus.UPLOADED
