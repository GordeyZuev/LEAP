"""Torn Prometheus mmap files must not 500 GET /metrics."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from prometheus_client.mmap_dict import MmapedDict, mmap_key

from api.observability.metrics import (
    _build_metrics_response,
    _merge_multiproc_files,
    handler_section_duration_seconds,
    increment_metric,
    track_handler_section,
)


def _write_corrupt_utf8_mmap(path: Path) -> None:
    encoded = b"a" * 167 + bytes([0x98]) + b"b" * 32
    encoded_len = len(encoded)
    pad = 8 - (encoded_len + 4) % 8
    padded_len = encoded_len + pad
    used = 8 + 4 + padded_len + 16
    buf = bytearray(used)
    struct.pack_into("i", buf, 0, used)
    struct.pack_into("i", buf, 8, encoded_len)
    buf[12 : 12 + encoded_len] = encoded
    struct.pack_into("dd", buf, 12 + padded_len, 1.0, 0.0)
    path.write_bytes(buf)


@pytest.mark.unit
def test_merge_skips_corrupt_mmap_and_keeps_good_file(tmp_path: Path) -> None:
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    store = MmapedDict(str(api_dir / "counter_1.db"))
    store.write_value(mmap_key("leap_test_total", "leap_test_total", [], [], "help"), 3.0, 0.0)
    store.close()
    _write_corrupt_utf8_mmap(tmp_path / "counter_2.db")

    metrics = list(_merge_multiproc_files(str(tmp_path)))

    assert {metric.name for metric in metrics} == {"leap_test_total"}


@pytest.mark.unit
def test_merge_combines_same_pid_files_from_isolated_component_directories(tmp_path: Path) -> None:
    for component, value in (("api", 2.0), ("celery", 3.0)):
        component_dir = tmp_path / component
        component_dir.mkdir()
        store = MmapedDict(str(component_dir / "counter_1.db"))
        store.write_value(mmap_key("leap_test_total", "leap_test_total", [], [], "help"), value, 0.0)
        store.close()

    metrics = list(_merge_multiproc_files(str(tmp_path)))

    assert len(metrics) == 1
    assert metrics[0].name == "leap_test_total"
    assert metrics[0].samples[0].value == 5.0


@pytest.mark.unit
def test_handler_metric_write_is_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_labels):
        raise UnicodeDecodeError("utf-8", b"\x98", 0, 1, "invalid start byte")

    monkeypatch.setattr(handler_section_duration_seconds, "labels", _boom)

    with track_handler_section("test"):
        pass

    with pytest.raises(RuntimeError, match="business failure"):
        with track_handler_section("test"):
            raise RuntimeError("business failure")


@pytest.mark.unit
def test_counter_write_is_fail_open() -> None:
    class BrokenCounter:
        _name = "broken_total"

        def inc(self, _amount: float) -> None:
            raise UnicodeDecodeError("utf-8", b"\x98", 0, 1, "invalid start byte")

    increment_metric(BrokenCounter())


@pytest.mark.unit
def test_metrics_response_200_when_render_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)

    def _boom(_registry):
        raise UnicodeDecodeError("utf-8", b"a" * 168, 167, 168, "invalid start byte")

    monkeypatch.setattr("api.observability.metrics.generate_latest", _boom)

    response = _build_metrics_response()

    assert response.status_code == 200
    assert response.body == b""
