"""Docker healthcheck for a Celery worker or Beat process and its dependencies."""

from __future__ import annotations

import os
import subprocess
import sys

import redis


def main() -> None:
    worker_pattern = os.getenv("CELERY_HEALTH_WORKER_PATTERN", r"celery -A api.celery_app worker")
    if subprocess.call(
        ["/usr/bin/pgrep", "-f", worker_pattern],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ):
        sys.exit(1)

    url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    client = redis.from_url(url, socket_connect_timeout=3)
    client.ping()

    # Queue depth is a saturation signal, not liveness: long jobs can keep it
    # unchanged while the worker is healthy. Monitor it outside Docker health.
    database_host = os.environ.get("DATABASE_HOST", "postgres")
    database_port = os.environ.get("DATABASE_PORT", "5432")
    database_user = os.environ.get("DATABASE_USERNAME", "postgres")
    if subprocess.call(
        ["/usr/bin/pg_isready", "-h", database_host, "-p", database_port, "-U", database_user],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3,
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
