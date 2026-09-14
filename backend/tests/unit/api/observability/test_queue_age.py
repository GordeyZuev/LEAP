"""Queue-age tracker must ignore Beat leftover ids that are not in the broker."""

from __future__ import annotations

import json

import pytest

from api.observability.metrics import (
    ENQUEUE_KEY_PREFIX,
    _task_id_from_broker_payload,
    prune_enqueue_tracker,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self.lists: dict[str, list[str]] = {}

    def zremrangebyscore(self, key: str, _min: float, max_score: float) -> int:
        zset = self.zsets.get(key, {})
        drop = [m for m, s in zset.items() if s <= max_score]
        for member in drop:
            del zset[member]
        return len(drop)

    def zrange(self, key: str, start: int, end: int, withscores: bool = False):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda pair: pair[1])
        if not items:
            return []
        if end == -1:
            sliced = items[start:]
        else:
            sliced = items[start : end + 1]
        if withscores:
            return sliced
        return [m for m, _ in sliced]

    def zrem(self, key: str, member: str) -> int:
        zset = self.zsets.get(key, {})
        if member in zset:
            del zset[member]
            return 1
        return 0

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]


def _broker_msg(task_id: str) -> str:
    return json.dumps({"headers": {"id": task_id, "task": "maintenance.cleanup_recording_files"}})


@pytest.mark.unit
def test_task_id_from_broker_payload_reads_headers() -> None:
    assert _task_id_from_broker_payload(_broker_msg("abc-1")) == "abc-1"
    assert _task_id_from_broker_payload("not-json") is None


@pytest.mark.unit
def test_orphan_tracker_dropped_when_broker_empty() -> None:
    redis = _FakeRedis()
    now = 1_000_000.0
    key = f"{ENQUEUE_KEY_PREFIX}maintenance"
    redis.zsets[key] = {"abcaffeb-ghost": now - 86400}

    age = prune_enqueue_tracker(redis, "maintenance", now)

    assert age == 0.0
    assert redis.zsets[key] == {}


@pytest.mark.unit
def test_recent_enqueue_kept_during_publish_race() -> None:
    redis = _FakeRedis()
    now = 1_000_000.0
    key = f"{ENQUEUE_KEY_PREFIX}downloads"
    redis.zsets[key] = {"just-published": now - 5}

    age = prune_enqueue_tracker(redis, "downloads", now)

    assert age == pytest.approx(5.0)
    assert "just-published" in redis.zsets[key]


@pytest.mark.unit
def test_ghost_dropped_when_real_task_is_pending() -> None:
    redis = _FakeRedis()
    now = 1_000_000.0
    key = f"{ENQUEUE_KEY_PREFIX}maintenance"
    redis.zsets[key] = {
        "abcaffeb-ghost": now - 86400,
        "663119a3-real": now - 12,
    }
    redis.lists["maintenance"] = [_broker_msg("663119a3-real")]

    age = prune_enqueue_tracker(redis, "maintenance", now)

    assert age == pytest.approx(12.0)
    assert redis.zsets[key] == {"663119a3-real": now - 12}
