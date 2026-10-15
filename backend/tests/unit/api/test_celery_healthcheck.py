"""Celery health checks report process and dependency readiness."""

from unittest.mock import ANY, MagicMock, call

import pytest

from scripts.celery_worker_healthcheck import main


@pytest.mark.unit
def test_worker_health_does_not_treat_a_long_queue_as_dead(mocker, monkeypatch):
    monkeypatch.setenv("CELERY_HEALTH_WORKER_PATTERN", "celery.*--queues=previews")
    monkeypatch.setenv("DATABASE_HOST", "postgres")
    redis = mocker.patch("scripts.celery_worker_healthcheck.redis.from_url", return_value=MagicMock())
    process = mocker.patch("scripts.celery_worker_healthcheck.subprocess.call", side_effect=[0, 0])

    main()

    redis.return_value.ping.assert_called_once_with()
    assert process.call_args_list == [
        call(
            ["/usr/bin/pgrep", "-f", "celery.*--queues=previews"],
            stdout=ANY,
            stderr=ANY,
        ),
        call(
            ["/usr/bin/pg_isready", "-h", "postgres", "-p", "5432", "-U", "postgres"],
            stdout=ANY,
            stderr=ANY,
            timeout=3,
        ),
    ]


@pytest.mark.unit
def test_worker_health_fails_when_database_is_unavailable(mocker):
    mocker.patch("scripts.celery_worker_healthcheck.redis.from_url", return_value=MagicMock())
    mocker.patch("scripts.celery_worker_healthcheck.subprocess.call", side_effect=[0, 1])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
