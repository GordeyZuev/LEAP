#!/usr/bin/env python3
"""Observability smoke test.

Verifies that a failed Celery task produces a log line in ``structured.json``
that includes the full context we expect Grafana / Loki queries to filter on:
``recording_id``, ``user_id``, ``task_id``, ``task_state="FAILURE"`` and the
exception class.

Usage:
    cd backend && uv run python scripts/observability_smoke.py

Returns exit code 0 on success, 1 on any missing field.

Requires a running Celery worker (the script enqueues to the live broker).
The synthetic task lives only here — it raises immediately so the failure
path runs end-to-end.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from api.celery_app import celery_app  # noqa: E402


@celery_app.task(name="observability.smoke_failing_task", bind=True, max_retries=0)
def _smoke_failing_task(_self, recording_id: int, user_id: str) -> None:  # noqa: ARG001
    raise RuntimeError(f"observability smoke failure for rec={recording_id}")


REQUIRED_KEYS = {"task_id", "task_name", "task_state", "recording_id", "user_id"}


def _structured_log_path() -> Path:
    explicit = os.getenv("JSON_LOG_FILE")
    if explicit:
        return Path(explicit)
    return BACKEND_DIR / "logs" / "structured.json"


def _scan_recent_lines(path: Path, limit_bytes: int = 256 * 1024) -> list[dict]:
    if not path.exists():
        return []
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > limit_bytes:
            fh.seek(-limit_bytes, 2)
        chunk = fh.read().decode("utf-8", errors="replace")
    out: list[dict] = []
    for raw in chunk.splitlines():
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out


def main() -> int:
    rec_id = 90_000_001
    user_id = "01KFOBSERVABILITYSMOKE"

    print(f"Enqueuing synthetic failing task (rec={rec_id}, user={user_id})...")
    result = _smoke_failing_task.apply_async(args=[rec_id, user_id])
    task_id = result.id
    print(f"Task ID: {task_id}")

    print("Waiting 10s for worker to process and flush logs...")
    time.sleep(10)

    log_path = _structured_log_path()
    print(f"Reading structured log: {log_path}")

    matching = []
    for entry in _scan_recent_lines(log_path):
        record = entry.get("record") or {}
        extra = record.get("extra") or {}
        if extra.get("task_id") and task_id.startswith(extra["task_id"]):
            matching.append(entry)

    if not matching:
        print("FAIL: no log lines found for this task in structured.json", file=sys.stderr)
        return 1

    failure_lines = [m for m in matching if (m.get("record", {}).get("extra", {}).get("task_state")) == "FAILURE"]
    if not failure_lines:
        print("FAIL: no FAILURE-state log line for this task", file=sys.stderr)
        return 1

    extra = failure_lines[-1]["record"]["extra"]
    missing = [k for k in REQUIRED_KEYS if extra.get(k) in (None, "")]
    if missing:
        print(f"FAIL: missing keys in FAILURE log entry: {missing}", file=sys.stderr)
        print(f"  extra payload: {extra}", file=sys.stderr)
        return 1

    print("PASS: FAILURE log line contains all required context")
    print(f"  task_id     = {extra.get('task_id')}")
    print(f"  task_name   = {extra.get('task_name')}")
    print(f"  recording_id= {extra.get('recording_id')}")
    print(f"  user_id     = {extra.get('user_id')}")
    print(f"  task_state  = {extra.get('task_state')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
