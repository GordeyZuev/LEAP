"""Product analytics — daily time series and breakdowns from Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.analytics import (
    AnalyticsBreakdown,
    AnalyticsSummary,
    DailyPoint,
    DailyUploadPoint,
    UserAnalyticsResponse,
)
from api.schemas.user.stats import StatsPeriod, TemplateStats
from api.services.share_observability import fill_daily_metrics
from database.models import OutputTargetModel, RecordingModel
from database.share_models import ShareAccessEventModel, ShareEventType
from database.template_models import RecordingTemplateModel
from models.recording import ProcessingStatus, TargetStatus
from utils.date_utils import parse_from_date_to_datetime, parse_to_date_to_datetime

MAX_ANALYTICS_RANGE_DAYS = 366


def default_analytics_range(days: int = 28) -> tuple[str, str]:
    """Return inclusive (from, to) ISO dates ending today (UTC)."""
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


_DAILY_METRIC_KEYS = (
    "recordings_created",
    "transcription_minutes",
    "transcription_jobs",
    "share_views",
    "share_downloads",
    "failed_recordings",
    "active_users",
)


class AnalyticsRangeError(ValueError):
    """Invalid analytics date range."""


def parse_analytics_range(from_date: str, to_date: str) -> tuple[date, date, datetime, datetime]:
    """Parse inclusive calendar range; raises AnalyticsRangeError on invalid input."""
    start_dt = parse_from_date_to_datetime(from_date)
    end_dt = parse_to_date_to_datetime(to_date)
    start_d = start_dt.date()
    end_d = end_dt.date()
    if start_d > end_d:
        raise AnalyticsRangeError("'from' must be <= 'to'")
    span = (end_d - start_d).days + 1
    if span > MAX_ANALYTICS_RANGE_DAYS:
        raise AnalyticsRangeError(f"Date range must not exceed {MAX_ANALYTICS_RANGE_DAYS} days")
    return start_d, end_d, start_dt, end_dt


def analytics_range_http_error(exc: AnalyticsRangeError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


class AnalyticsService:
    """Aggregate product metrics by calendar day (UTC)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_analytics(self, user_id: str, from_date: str, to_date: str) -> UserAnalyticsResponse:
        start_d, end_d, start_dt, end_dt = parse_analytics_range(from_date, to_date)
        period = StatsPeriod(**{"from": start_d, "to": end_d})

        metrics_by_date = await self._load_daily_metrics(user_id, start_dt, end_dt, include_active_users=False)
        daily = self._build_daily_points(metrics_by_date, start_d, end_d, include_active_users=False)
        daily_uploads = await self._daily_uploads(user_id, start_dt, end_dt, start_d, end_d)
        summary = self._summarize(daily, daily_uploads)
        breakdown = await self._breakdowns(user_id, start_dt, end_dt)

        return UserAnalyticsResponse(
            period=period,
            daily=daily,
            daily_uploads=daily_uploads,
            summary=summary,
            breakdown=breakdown,
        )

    async def get_platform_analytics(self, from_date: str, to_date: str) -> UserAnalyticsResponse:
        start_d, end_d, start_dt, end_dt = parse_analytics_range(from_date, to_date)
        period = StatsPeriod(**{"from": start_d, "to": end_d})

        metrics_by_date = await self._load_daily_metrics(None, start_dt, end_dt, include_active_users=True)
        daily = self._build_daily_points(metrics_by_date, start_d, end_d, include_active_users=True)
        daily_uploads = await self._daily_uploads(None, start_dt, end_dt, start_d, end_d)
        summary = self._summarize(daily, daily_uploads)
        unique_active = await self._unique_active_users(start_dt, end_dt)
        summary.active_users_unique = unique_active
        breakdown = await self._breakdowns(None, start_dt, end_dt)

        return UserAnalyticsResponse(
            period=period,
            daily=daily,
            daily_uploads=daily_uploads,
            summary=summary,
            breakdown=breakdown,
        )

    async def _load_daily_metrics(
        self,
        user_id: str | None,
        start_dt: datetime,
        end_dt: datetime,
        *,
        include_active_users: bool,
    ) -> dict[date, dict[str, float | int | None]]:
        metrics: dict[date, dict[str, float | int | None]] = {}

        def bump(day: date, key: str, value: float | int) -> None:
            metrics.setdefault(day, {})
            metrics[day][key] = value

        for day, count in await self._recordings_by_day(user_id, start_dt, end_dt):
            bump(day, "recordings_created", count)

        for day, minutes, jobs in await self._transcription_by_day(user_id, start_dt, end_dt):
            bump(day, "transcription_minutes", round(minutes, 2))
            bump(day, "transcription_jobs", jobs)

        for day, views, downloads in await self._share_by_day(user_id, start_dt, end_dt):
            bump(day, "share_views", views)
            bump(day, "share_downloads", downloads)

        for day, count in await self._failed_by_day(user_id, start_dt, end_dt):
            bump(day, "failed_recordings", count)

        if include_active_users:
            for day, count in await self._active_users_by_day(start_dt, end_dt):
                bump(day, "active_users", count)

        return metrics

    async def _recordings_by_day(
        self, user_id: str | None, start_dt: datetime, end_dt: datetime
    ) -> list[tuple[date, int]]:
        day_col = func.date_trunc("day", RecordingModel.created_at).label("day")
        q = (
            select(day_col, func.count())
            .where(
                RecordingModel.deleted.is_(False),
                RecordingModel.created_at >= start_dt,
                RecordingModel.created_at <= end_dt,
            )
            .group_by(day_col)
        )
        if user_id:
            q = q.where(RecordingModel.user_id == user_id)
        result = await self.session.execute(q)
        return [(row[0].date(), int(row[1])) for row in result.all() if row[0]]

    async def _transcription_by_day(
        self, user_id: str | None, start_dt: datetime, end_dt: datetime
    ) -> list[tuple[date, float, int]]:
        if user_id:
            sql = text(
                """
                SELECT sub.day::date AS day,
                       ROUND(SUM(sub.minutes)::numeric, 2) AS minutes,
                       COUNT(*)::int AS jobs
                FROM (
                    SELECT DISTINCT ON (st.recording_id, date_trunc('day', st.completed_at))
                        date_trunc('day', st.completed_at) AS day,
                        (r.final_duration / 60.0) AS minutes
                    FROM stage_timings st
                    JOIN recordings r ON r.id = st.recording_id
                    WHERE st.stage_type = 'TRANSCRIBE'
                      AND st.status = 'COMPLETED'
                      AND st.substep IS NULL
                      AND st.completed_at >= :start_dt
                      AND st.completed_at <= :end_dt
                      AND r.final_duration IS NOT NULL
                      AND r.final_duration > 0
                      AND r.deleted IS FALSE
                      AND r.user_id = :user_id
                    ORDER BY st.recording_id, date_trunc('day', st.completed_at), st.completed_at DESC
                ) sub
                GROUP BY sub.day
                ORDER BY sub.day
                """
            )
            params = {"start_dt": start_dt, "end_dt": end_dt, "user_id": user_id}
        else:
            sql = text(
                """
                SELECT sub.day::date AS day,
                       ROUND(SUM(sub.minutes)::numeric, 2) AS minutes,
                       COUNT(*)::int AS jobs
                FROM (
                    SELECT DISTINCT ON (st.recording_id, date_trunc('day', st.completed_at))
                        date_trunc('day', st.completed_at) AS day,
                        (r.final_duration / 60.0) AS minutes
                    FROM stage_timings st
                    JOIN recordings r ON r.id = st.recording_id
                    WHERE st.stage_type = 'TRANSCRIBE'
                      AND st.status = 'COMPLETED'
                      AND st.substep IS NULL
                      AND st.completed_at >= :start_dt
                      AND st.completed_at <= :end_dt
                      AND r.final_duration IS NOT NULL
                      AND r.final_duration > 0
                      AND r.deleted IS FALSE
                    ORDER BY st.recording_id, date_trunc('day', st.completed_at), st.completed_at DESC
                ) sub
                GROUP BY sub.day
                ORDER BY sub.day
                """
            )
            params = {"start_dt": start_dt, "end_dt": end_dt}
        result = await self.session.execute(sql, params)
        return [(row.day, float(row.minutes or 0), int(row.jobs or 0)) for row in result.all()]

    async def _share_by_day(
        self, user_id: str | None, start_dt: datetime, end_dt: datetime
    ) -> list[tuple[date, int, int]]:
        day_col = func.date_trunc("day", ShareAccessEventModel.created_at).label("day")
        views_col = func.sum(case((ShareAccessEventModel.event_type == ShareEventType.PAGE_VIEW, 1), else_=0)).label(
            "views"
        )
        downloads_col = func.sum(
            case((ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD, 1), else_=0)
        ).label("downloads")
        q = (
            select(day_col, views_col, downloads_col)
            .where(
                ShareAccessEventModel.created_at >= start_dt,
                ShareAccessEventModel.created_at <= end_dt,
            )
            .group_by(day_col)
        )
        if user_id:
            q = q.where(ShareAccessEventModel.owner_user_id == user_id)
        result = await self.session.execute(q)
        rows: list[tuple[date, int, int]] = []
        for day, views, downloads in result.all():
            if day:
                rows.append((day.date(), int(views or 0), int(downloads or 0)))
        return rows

    async def _failed_by_day(self, user_id: str | None, start_dt: datetime, end_dt: datetime) -> list[tuple[date, int]]:
        day_col = func.date_trunc("day", RecordingModel.failed_at).label("day")
        q = (
            select(day_col, func.count())
            .where(
                RecordingModel.failed.is_(True),
                RecordingModel.failed_at.is_not(None),
                RecordingModel.failed_at >= start_dt,
                RecordingModel.failed_at <= end_dt,
            )
            .group_by(day_col)
        )
        if user_id:
            q = q.where(RecordingModel.user_id == user_id)
        result = await self.session.execute(q)
        return [(row[0].date(), int(row[1])) for row in result.all() if row[0]]

    async def _active_users_by_day(self, start_dt: datetime, end_dt: datetime) -> list[tuple[date, int]]:
        day_col = func.date_trunc("day", RecordingModel.created_at).label("day")
        result = await self.session.execute(
            select(day_col, func.count(func.distinct(RecordingModel.user_id)))
            .where(
                RecordingModel.deleted.is_(False),
                RecordingModel.user_id.is_not(None),
                RecordingModel.created_at >= start_dt,
                RecordingModel.created_at <= end_dt,
            )
            .group_by(day_col)
        )
        return [(row[0].date(), int(row[1])) for row in result.all() if row[0]]

    async def _unique_active_users(self, start_dt: datetime, end_dt: datetime) -> int:
        result = await self.session.scalar(
            select(func.count(func.distinct(RecordingModel.user_id))).where(
                RecordingModel.deleted.is_(False),
                RecordingModel.user_id.is_not(None),
                RecordingModel.created_at >= start_dt,
                RecordingModel.created_at <= end_dt,
            )
        )
        return int(result or 0)

    async def _daily_uploads(
        self,
        user_id: str | None,
        start_dt: datetime,
        end_dt: datetime,
        start_d: date,
        end_d: date,
    ) -> list[DailyUploadPoint]:
        day_col = func.date_trunc("day", OutputTargetModel.uploaded_at).label("day")
        q = (
            select(day_col, OutputTargetModel.target_type, func.count())
            .where(
                OutputTargetModel.status == TargetStatus.UPLOADED,
                OutputTargetModel.uploaded_at.is_not(None),
                OutputTargetModel.uploaded_at >= start_dt,
                OutputTargetModel.uploaded_at <= end_dt,
            )
            .group_by(day_col, OutputTargetModel.target_type)
        )
        if user_id:
            q = q.where(OutputTargetModel.user_id == user_id)
        result = await self.session.execute(q)

        by_date: dict[date, dict[str, int]] = {}
        for day, platform, count in result.all():
            if not day:
                continue
            d = day.date()
            by_date.setdefault(d, {})
            platform_key = str(platform.value if hasattr(platform, "value") else platform)
            by_date[d][platform_key] = int(count)

        series: list[DailyUploadPoint] = []
        current = start_d
        while current <= end_d:
            series.append(DailyUploadPoint(date=current, by_platform=by_date.get(current, {})))
            current += timedelta(days=1)
        return series

    async def _breakdowns(self, user_id: str | None, start_dt: datetime, end_dt: datetime) -> AnalyticsBreakdown:
        uploads_by_platform = await self._uploads_by_platform(user_id, start_dt, end_dt)
        recordings_by_status = await self._recordings_by_status(user_id, start_dt, end_dt)
        top_templates = await self._top_templates(user_id, start_dt, end_dt)
        downloads_by_type = await self._downloads_by_type(user_id, start_dt, end_dt)
        return AnalyticsBreakdown(
            uploads_by_platform=uploads_by_platform,
            recordings_by_status=recordings_by_status,
            top_templates=top_templates,
            downloads_by_type=downloads_by_type,
        )

    async def _uploads_by_platform(self, user_id: str | None, start_dt: datetime, end_dt: datetime) -> dict[str, int]:
        q = (
            select(OutputTargetModel.target_type, func.count())
            .where(
                OutputTargetModel.status == TargetStatus.UPLOADED,
                OutputTargetModel.uploaded_at.is_not(None),
                OutputTargetModel.uploaded_at >= start_dt,
                OutputTargetModel.uploaded_at <= end_dt,
            )
            .group_by(OutputTargetModel.target_type)
        )
        if user_id:
            q = q.where(OutputTargetModel.user_id == user_id)
        result = await self.session.execute(q)
        return {
            str(platform.value if hasattr(platform, "value") else platform): int(count)
            for platform, count in result.all()
        }

    async def _recordings_by_status(self, user_id: str | None, start_dt: datetime, end_dt: datetime) -> dict[str, int]:
        q = (
            select(RecordingModel.status, func.count())
            .where(
                RecordingModel.deleted.is_(False),
                RecordingModel.created_at >= start_dt,
                RecordingModel.created_at <= end_dt,
            )
            .group_by(RecordingModel.status)
        )
        if user_id:
            q = q.where(RecordingModel.user_id == user_id)
        result = await self.session.execute(q)
        return {str(row[0]): int(row[1]) for row in result.all()}

    async def _top_templates(
        self, user_id: str | None, start_dt: datetime, end_dt: datetime, limit: int = 10
    ) -> list[TemplateStats]:
        q = (
            select(
                RecordingModel.template_id,
                RecordingTemplateModel.name,
                func.count(RecordingModel.id),
            )
            .outerjoin(RecordingTemplateModel, RecordingModel.template_id == RecordingTemplateModel.id)
            .where(
                RecordingModel.deleted.is_(False),
                RecordingModel.status == ProcessingStatus.READY,
                RecordingModel.template_id.isnot(None),
                RecordingModel.created_at >= start_dt,
                RecordingModel.created_at <= end_dt,
            )
            .group_by(RecordingModel.template_id, RecordingTemplateModel.name)
            .order_by(func.count(RecordingModel.id).desc())
            .limit(limit)
        )
        if user_id:
            q = q.where(RecordingModel.user_id == user_id)
        result = await self.session.execute(q)
        return [TemplateStats(template_id=row[0], template_name=row[1], count=row[2]) for row in result.all()]

    async def _downloads_by_type(self, user_id: str | None, start_dt: datetime, end_dt: datetime) -> dict[str, int]:
        q = (
            select(ShareAccessEventModel.artifact_type, func.count())
            .where(
                ShareAccessEventModel.event_type == ShareEventType.FILE_DOWNLOAD,
                ShareAccessEventModel.created_at >= start_dt,
                ShareAccessEventModel.created_at <= end_dt,
                ShareAccessEventModel.artifact_type.is_not(None),
            )
            .group_by(ShareAccessEventModel.artifact_type)
        )
        if user_id:
            q = q.where(ShareAccessEventModel.owner_user_id == user_id)
        result = await self.session.execute(q)
        return {str(artifact_type): int(count) for artifact_type, count in result.all()}

    def _build_daily_points(
        self,
        metrics_by_date: dict[date, dict[str, float | int | None]],
        start_d: date,
        end_d: date,
        *,
        include_active_users: bool,
    ) -> list[DailyPoint]:
        keys = _DAILY_METRIC_KEYS if include_active_users else _DAILY_METRIC_KEYS[:-1]
        rows = fill_daily_metrics(metrics_by_date, from_date=start_d, to_date=end_d, metric_keys=keys)
        points: list[DailyPoint] = []
        for row in rows:
            day = row["date"]
            assert isinstance(day, date)
            points.append(
                DailyPoint(
                    date=day,
                    recordings_created=int(row.get("recordings_created") or 0),
                    transcription_minutes=float(row.get("transcription_minutes") or 0),
                    transcription_jobs=int(row.get("transcription_jobs") or 0),
                    share_views=int(row.get("share_views") or 0),
                    share_downloads=int(row.get("share_downloads") or 0),
                    failed_recordings=int(row.get("failed_recordings") or 0),
                    active_users=int(row["active_users"])
                    if include_active_users and row.get("active_users") is not None
                    else None,
                )
            )
        return points

    def _summarize(
        self,
        daily: list[DailyPoint],
        daily_uploads: list[DailyUploadPoint],
    ) -> AnalyticsSummary:
        uploads_total = sum(sum(day.by_platform.values()) for day in daily_uploads)
        return AnalyticsSummary(
            recordings_created=sum(p.recordings_created for p in daily),
            transcription_minutes=round(sum(p.transcription_minutes for p in daily), 2),
            transcription_jobs=sum(p.transcription_jobs for p in daily),
            share_views=sum(p.share_views for p in daily),
            share_downloads=sum(p.share_downloads for p in daily),
            failed_recordings=sum(p.failed_recordings for p in daily),
            active_users_unique=None,
            uploads_total=uploads_total,
        )
