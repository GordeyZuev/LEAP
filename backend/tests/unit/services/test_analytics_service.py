"""Unit tests for analytics range parsing and daily zero-fill."""

from datetime import date

import pytest

from api.services.analytics_service import AnalyticsRangeError, parse_analytics_range
from api.services.share_observability import fill_daily_metrics, fill_daily_series


@pytest.mark.unit
class TestParseAnalyticsRange:
    def test_valid_range(self) -> None:
        start_d, end_d, start_dt, end_dt = parse_analytics_range("2026-01-01", "2026-01-31")
        assert start_d == date(2026, 1, 1)
        assert end_d == date(2026, 1, 31)
        assert start_dt.date() == start_d
        assert end_dt.date() == end_d

    def test_rejects_inverted_range(self) -> None:
        with pytest.raises(AnalyticsRangeError, match="from"):
            parse_analytics_range("2026-02-01", "2026-01-01")

    def test_rejects_range_over_max_days(self) -> None:
        with pytest.raises(AnalyticsRangeError, match="366"):
            parse_analytics_range("2024-01-01", "2026-01-01")


@pytest.mark.unit
class TestFillDailyMetrics:
    def test_zero_fills_gaps(self) -> None:
        metrics = {
            date(2026, 3, 1): {"recordings_created": 2},
            date(2026, 3, 3): {"recordings_created": 1},
        }
        rows = fill_daily_metrics(
            metrics,
            from_date=date(2026, 3, 1),
            to_date=date(2026, 3, 3),
            metric_keys=("recordings_created",),
        )
        assert len(rows) == 3
        assert rows[0]["recordings_created"] == 2
        assert rows[1]["recordings_created"] == 0
        assert rows[2]["recordings_created"] == 1


@pytest.mark.unit
class TestFillDailySeries:
    def test_custom_date_range(self) -> None:
        from datetime import UTC, datetime

        aggregates = [(datetime(2026, 3, 2, 12, 0, tzinfo=UTC), 5, 1)]
        series = fill_daily_series(
            aggregates,
            from_date=date(2026, 3, 1),
            to_date=date(2026, 3, 3),
        )
        assert len(series) == 3
        assert series[0] == (date(2026, 3, 1), 0, 0)
        assert series[1] == (date(2026, 3, 2), 5, 1)
        assert series[2] == (date(2026, 3, 3), 0, 0)
