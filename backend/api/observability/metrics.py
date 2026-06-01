"""Prometheus instrumentation for the FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from logger import get_logger

logger = get_logger("observability")

_EXCLUDED_PATHS: tuple[str, ...] = ("/api/v1/health", "/metrics")


def setup_prometheus(app: FastAPI, *, enabled: bool) -> None:
    """Mount /metrics under the ``leap_http_*`` namespace.

    The ``handler`` label is always the FastAPI route template
    (``/api/v1/recordings/{id}``) so Prometheus cardinality stays bounded.
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
            latency_lowr_buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            latency_highr_buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
        )
    )
    instrumentator.add(metrics.request_size(metric_namespace="leap"))
    instrumentator.add(metrics.response_size(metric_namespace="leap"))

    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        tags=["observability"],
    )
    logger.info("Prometheus instrumentation enabled at /metrics")
