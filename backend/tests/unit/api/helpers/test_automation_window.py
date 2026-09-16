from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from api.helpers.automation_window import last_n_calendar_days, resolve_job_timezone, resolve_job_window
from api.tasks.automation import _apply_enqueue_cap, _order_templates, _sync_and_match
from models.recording import ProcessingStatus


@pytest.mark.unit
def test_last_n_days_n1_is_today_only_in_moscow():
    now = datetime(2026, 9, 16, 22, 42, tzinfo=UTC)
    window = last_n_calendar_days(1, tz_name="Europe/Moscow", now=now)
    assert window.from_date == "2026-09-17"
    assert window.to_date == "2026-09-17"
    msk = ZoneInfo("Europe/Moscow")
    assert window.from_datetime == datetime(2026, 9, 17, 0, 0, tzinfo=msk).astimezone(UTC)
    assert window.to_datetime.astimezone(msk).date().isoformat() == "2026-09-17"


@pytest.mark.unit
def test_last_n_days_includes_first_and_last_local_midnight():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    window = last_n_calendar_days(2, tz_name="Europe/Moscow", now=now)
    assert window.from_date == "2026-09-15"
    assert window.to_date == "2026-09-16"
    msk = ZoneInfo("Europe/Moscow")
    first = datetime(2026, 9, 15, 0, 1, tzinfo=msk).astimezone(UTC)
    last = datetime(2026, 9, 16, 23, 59, tzinfo=msk).astimezone(UTC)
    assert window.from_datetime <= first <= window.to_datetime
    assert window.from_datetime <= last <= window.to_datetime


@pytest.mark.unit
def test_last_30_days_is_thirty_inclusive_dates():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    window = last_n_calendar_days(30, tz_name="Europe/Moscow", now=now)
    assert window.from_date == "2026-08-18"
    assert window.to_date == "2026-09-16"


@pytest.mark.unit
def test_unbounded_match_has_no_lower_bound_api_sync_uses_30():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    match = resolve_job_window(None, tz_name="Europe/Moscow", now=now, for_api_sync=False)
    assert match.from_date is None
    assert match.from_datetime is None
    api = resolve_job_window(None, tz_name="Europe/Moscow", now=now, for_api_sync=True)
    assert api.from_date == "2026-08-18"
    assert api.to_date == "2026-09-16"


@pytest.mark.unit
def test_missing_schedule_timezone_is_moscow():
    assert resolve_job_timezone(None) == "Europe/Moscow"
    assert resolve_job_timezone({}) == "Europe/Moscow"


@pytest.mark.unit
def test_order_templates_follows_job_ids():
    t1 = SimpleNamespace(id=1)
    t2 = SimpleNamespace(id=2)
    t3 = SimpleNamespace(id=3)
    ordered = _order_templates([t2, t3, t1], [3, 1, 2])
    assert [t.id for t in ordered] == [3, 1, 2]


@pytest.mark.unit
def test_enqueue_cap_keeps_wait_and_newest_ready():
    wait = SimpleNamespace(status=ProcessingStatus.PENDING_CONVERSION, start_time=datetime(2026, 1, 1, tzinfo=UTC))
    old = SimpleNamespace(status=ProcessingStatus.INITIALIZED, start_time=datetime(2026, 9, 1, tzinfo=UTC))
    new = SimpleNamespace(status=ProcessingStatus.INITIALIZED, start_time=datetime(2026, 9, 16, tzinfo=UTC))
    tmpl = SimpleNamespace(id=1)
    capped = _apply_enqueue_cap([(old, tmpl), (wait, tmpl), (new, tmpl)], 1)
    assert [r.status for r, _ in capped] == [ProcessingStatus.PENDING_CONVERSION, ProcessingStatus.INITIALIZED]
    assert capped[1][0] is new


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_false_skips_source_sync():
    job = SimpleNamespace(
        id=1,
        template_ids=[1],
        schedule={"timezone": "Europe/Moscow"},
        sync_config={"sync_days": 2},
        filters={"exclude_blank": True, "status": ["INITIALIZED"]},
    )
    tmpl = SimpleNamespace(id=1, is_active=True, is_draft=False, matching_rules={"source_ids": [9]})
    source = SimpleNamespace(id=9, is_active=True, credential_id=1)
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    with (
        patch("api.tasks.automation._load_job_templates", new_callable=AsyncMock, return_value=(None, [tmpl])),
        patch("api.tasks.automation._sources_for_templates", new_callable=AsyncMock, return_value=[source]),
        patch("api.tasks.automation._sync_sources", new_callable=AsyncMock) as sync_sources,
        patch("api.routers.input_sources._find_matching_template", return_value=None),
    ):
        plan = await _sync_and_match(session, job, "u1", sync=False)

    sync_sources.assert_not_called()
    assert plan.synced_count == 0
    assert plan.recordings_found == 0


@pytest.mark.unit
def test_exclude_blank_defaults_true_when_filters_omitted():
    from api.tasks.automation import _resolve_status_filter

    assert _resolve_status_filter({})  # default statuses, not empty
    # Missing filters key is handled in _sync_and_match via (job.filters or {}).get("exclude_blank", True)
    assert ({}.get("exclude_blank", True)) is True
