"""Docker healthcheck for celery_worker: process alive, Redis up, queues not stuck."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import redis

QUEUES = ("async_operations", "downloads", "processing_cpu", "uploads", "maintenance", "celery")
MARKER = Path("/tmp/celery_worker_health_queue")
STUCK_SEC = int(os.getenv("CELERY_HEALTH_STUCK_SEC", "300"))


def main() -> None:
    if subprocess.call(
        ["/usr/bin/pgrep", "-f", r"celery -A api.celery_app worker"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ):
        sys.exit(1)

    url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    client = redis.from_url(url, socket_connect_timeout=3)
    client.ping()

    depth = sum(int(client.llen(q)) for q in QUEUES)
    now = time.time()
    if depth == 0:
        MARKER.unlink(missing_ok=True)
        sys.exit(0)

    if MARKER.exists():
        try:
            prev_depth, since = MARKER.read_text().split()
            prev_depth, since = int(float(prev_depth)), float(since)
        except (OSError, ValueError):
            MARKER.write_text(f"{depth} {now}")
            sys.exit(0)
        if depth < prev_depth:
            MARKER.write_text(f"{depth} {now}")
            sys.exit(0)
        if now - since >= STUCK_SEC:
            sys.exit(1)
        sys.exit(0)

    MARKER.write_text(f"{depth} {now}")
    sys.exit(0)


if __name__ == "__main__":
    main()
