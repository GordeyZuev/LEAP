"""Prometheus instrumentation for the FastAPI app + custom LEAP metrics."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import redis
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from config.settings import get_settings
from logger import get_logger

logger = get_logger("observability")

_EXCLUDED_PATHS: tuple[str, ...] = (
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/metrics",
)

# ---------------------------------------------------------------------------
# Custom LEAP metrics
# ---------------------------------------------------------------------------
# Multiprocess mode: when PROMETHEUS_MULTIPROC_DIR is set, all processes
# (uvicorn workers + Celery workers) write metric observations to files in that
# shared directory. The /metrics endpoint reads and aggregates all files via
# MultiProcessCollector. Without the env var, single-process mode is used.

# Pipeline stage duration: download / trim / transcribe / extract_topics /
# generate_subtitles / upload. `status` is "success" or "failure".
pipeline_stage_duration_seconds = Histogram(
    "leap_pipeline_stage_duration_seconds",
    "Duration of a single pipeline stage execution.",
    labelnames=("stage", "platform", "status"),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1200, 3600, 7200),
)

# External API call duration — Fireworks ASR, DeepSeek, Yandex Disk, YouTube,
# VK, Zoom OAuth, etc. `endpoint` is a stable label (operation name).
external_api_duration_seconds = Histogram(
    "leap_external_api_duration_seconds",
    "Latency of outbound calls to external APIs.",
    labelnames=("provider", "endpoint", "status"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

share_page_views_total = Counter(
    "leap_share_page_views_total",
    "Public share page views counted after deduplication.",
)

share_downloads_total = Counter(
    "leap_share_downloads_total",
    "Public share artifact downloads.",
    labelnames=("artifact_type",),
)

# Hot-path sections inside handlers (poster batching, share item build, MTS prepare).
handler_section_duration_seconds = Histogram(
    "leap_handler_section_duration_seconds",
    "Time spent in named handler subsections.",
    labelnames=("section",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

_QUEUES_TRACKED = ("downloads", "uploads", "async_operations", "processing_cpu", "maintenance", "celery")
QUEUES_TRACKED = _QUEUES_TRACKED
ENQUEUE_KEY_PREFIX = "leap:enq:"
# Drop tracker members older than this — leftover ZSET rows, not a live backlog.
_STALE_ENQUEUE_SECONDS = 7 * 24 * 3600
# Beat/worker task-id mismatch leaves ZSET rows after the broker message is gone.
# Keep very new members (publish vs LLEN race); drop the rest if they are not pending.
_ORPHAN_ENQUEUE_SECONDS = 30
_BROKER_SCAN_LIMIT = 500


def _task_id_from_broker_payload(raw: object) -> str | None:
    """Extract a Celery task id from a Redis-broker list payload."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    headers = payload.get("headers")
    if isinstance(headers, dict) and headers.get("id"):
        return str(headers["id"])
    properties = payload.get("properties")
    if isinstance(properties, dict) and properties.get("correlation_id"):
        return str(properties["correlation_id"])
    return None


def prune_enqueue_tracker(client: redis.Redis, queue: str, now: float) -> float:
    """Drop tracker leftovers and return the oldest still-pending age in seconds.

    Beat can zadd a task id that the worker never sees (DatabaseScheduler vs the
    executed id). Those rows are not in the broker list. Members younger than
    `_ORPHAN_ENQUEUE_SECONDS` are kept so a scrape between zadd and LPUSH is not
    dropped. When the list has messages we cannot parse, the ZSET is left as-is.
    """
    key = f"{ENQUEUE_KEY_PREFIX}{queue}"
    client.zremrangebyscore(key, 0, now - _STALE_ENQUEUE_SECONDS)

    # redis-py types Redis commands as sync | Awaitable; this collector is sync-only.
    llen = int(cast("int", client.llen(queue)) or 0)
    pending_ids: set[str] = set()
    if llen:
        raw_items = cast("list[object]", client.lrange(queue, 0, min(llen, _BROKER_SCAN_LIMIT) - 1) or [])
        for raw in raw_items:
            task_id = _task_id_from_broker_payload(raw)
            if task_id:
                pending_ids.add(task_id)

    members = cast("list[tuple[object, float]]", client.zrange(key, 0, -1, withscores=True) or [])
    for member, score in members:
        member_s = str(member)
        age = now - float(score)
        if age < _ORPHAN_ENQUEUE_SECONDS:
            continue
        if llen == 0 or (pending_ids and member_s not in pending_ids):
            client.zrem(key, member)

    oldest = cast("list[tuple[object, float]]", client.zrange(key, 0, 0, withscores=True) or [])
    if not oldest:
        return 0.0
    return max(0.0, now - float(oldest[0][1]))


class _QueueAgeCollector:
    """Lazy collector — reads Redis on every Prometheus scrape.

    Lives in the API process; Celery workers/beat push enqueue timestamps to
    Redis via signal handlers. Keeping collection here avoids cross-process
    metric aggregation for a single number that only makes sense from the API.
    """

    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    def _redis(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(get_settings().celery.broker_url, decode_responses=True)
        return self._client

    def collect(self):
        gauge = GaugeMetricFamily(
            "leap_queue_oldest_task_age_seconds",
            "Age of the oldest pending task in a Celery queue, in seconds.",
            labels=["queue"],
        )
        try:
            client = self._redis()
            now = time.time()
            for queue in _QUEUES_TRACKED:
                gauge.add_metric([queue], prune_enqueue_tracker(client, queue, now))
        except Exception as exc:
            logger.warning("Queue age collector failed: {}", exc)
        yield gauge


_queue_age_collector = _QueueAgeCollector()


def _merge_multiproc_files(multiproc_dir: str):
    """Merge mmap files, skipping any torn .db so /metrics does not 500."""
    from prometheus_client.multiprocess import MultiProcessCollector

    usable: list[str] = []
    for path in Path(multiproc_dir).glob("*.db"):
        file = str(path)
        try:
            MultiProcessCollector.merge([file], accumulate=False)
        except Exception as exc:
            logger.warning("Skipping corrupt Prometheus mmap file {}: {}", file, exc)
            continue
        usable.append(file)
    if not usable:
        return []
    return MultiProcessCollector.merge(usable, accumulate=True)


class _SafeMultiProcessCollector:
    def collect(self):
        path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
        return _merge_multiproc_files(path) if path else []


_safe_multiproc_collector = _SafeMultiProcessCollector()


@contextmanager
def track_pipeline_stage(stage: str, platform: str = "n/a") -> Iterator[None]:
    """Time a pipeline stage and emit the histogram observation.

    Records "failure" when the wrapped block raises; otherwise "success".
    Re-raises any exception unchanged.
    """
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "failure"
        raise
    finally:
        elapsed = time.perf_counter() - start
        pipeline_stage_duration_seconds.labels(stage=stage, platform=platform, status=status).observe(elapsed)


@contextmanager
def track_handler_section(section: str) -> Iterator[None]:
    """Time a subsection of a request handler (for latency breakdown in Grafana)."""
    start = time.perf_counter()
    try:
        yield
    finally:
        handler_section_duration_seconds.labels(section=section).observe(time.perf_counter() - start)


@contextmanager
def track_external_api(provider: str, endpoint: str) -> Iterator[None]:
    """Time an outbound call to an external API."""
    start = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.perf_counter() - start
        external_api_duration_seconds.labels(provider=provider, endpoint=endpoint, status=status).observe(elapsed)


def _build_metrics_response() -> Response:
    """Aggregate metrics from all processes and return a Prometheus text response.

    In multiprocess mode (PROMETHEUS_MULTIPROC_DIR is set), reads metric files
    written by all uvicorn workers and Celery workers from the shared directory.
    The _QueueAgeCollector is always added — it generates live Redis data and
    is only meaningful from the API process.

    Torn mmap files are skipped so the scrape stays 200.
    """
    try:
        if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
            registry = CollectorRegistry()
            registry.register(_safe_multiproc_collector)
            registry.register(_queue_age_collector)
        else:
            registry = REGISTRY
        return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    except Exception as exc:
        logger.warning("Failed to render /metrics: {}", exc)
        return Response(content=b"", media_type=CONTENT_TYPE_LATEST)


def setup_prometheus(app: FastAPI, *, enabled: bool) -> None:
    """Mount /metrics under the ``leap_http_*`` namespace.

    The ``handler`` label is always the FastAPI route template
    (``/api/v1/recordings/{id}``) so Prometheus cardinality stays bounded.

    When PROMETHEUS_MULTIPROC_DIR is set, the /metrics endpoint aggregates
    metric files from all processes (API workers + Celery workers) via
    MultiProcessCollector, making pipeline stage durations visible.
    """
    if not enabled:
        logger.info("Prometheus instrumentation disabled")
        return

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_group_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=list(_EXCLUDED_PATHS),
        # inprogress_name is a literal — not auto-prefixed by metric_namespace.
        inprogress_name="leap_http_requests_inprogress",
        inprogress_labels=True,
    )
    # metric_subsystem intentionally omitted — the library already prefixes
    # the metric base name with ``http_``; setting subsystem="http" yields
    # the double-prefixed ``leap_http_http_*``.
    instrumentator.add(
        metrics.default(
            metric_namespace="leap",
            latency_lowr_buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            latency_highr_buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
        )
    )
    instrumentator.add(metrics.request_size(metric_namespace="leap"))
    instrumentator.add(metrics.response_size(metric_namespace="leap"))

    # Instrument request handlers but do NOT call .expose() — we add our own
    # /metrics route below to support multiprocess aggregation.
    instrumentator.instrument(app)

    # In single-process mode, the queue age collector lives in the global
    # registry and is called automatically on every scrape.
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        try:
            REGISTRY.register(_queue_age_collector)
        except ValueError:
            # Already registered — happens in dev autoreload.
            pass

    @app.get("/metrics", include_in_schema=False, tags=["observability"])
    def _metrics_endpoint() -> Response:
        return _build_metrics_response()

    logger.info("Prometheus instrumentation enabled at /metrics")
