"""Product analytics schemas (daily time series + breakdowns)."""

from datetime import date

from pydantic import BaseModel, Field

from api.schemas.user.stats import StatsPeriod, TemplateStats


class DailyPoint(BaseModel):
    """One calendar day of aggregated metrics."""

    date: date
    recordings_created: int = 0
    transcription_minutes: float = 0
    transcription_jobs: int = 0
    share_views: int = 0
    share_downloads: int = 0
    failed_recordings: int = 0
    active_users: int | None = Field(None, description="Platform-only: distinct users with a new recording")


class DailyUploadPoint(BaseModel):
    """Upload counts per platform for one day (stacked chart)."""

    date: date
    by_platform: dict[str, int] = Field(default_factory=dict)


class AnalyticsSummary(BaseModel):
    """Period totals derived from daily series."""

    recordings_created: int = 0
    transcription_minutes: float = 0
    transcription_jobs: int = 0
    share_views: int = 0
    share_downloads: int = 0
    failed_recordings: int = 0
    active_users_unique: int | None = Field(
        None, description="Platform-only: distinct users with ≥1 recording created in period"
    )
    uploads_total: int = 0


class AnalyticsBreakdown(BaseModel):
    """Non-daily aggregates for the selected period."""

    uploads_by_platform: dict[str, int] = Field(default_factory=dict)
    recordings_by_status: dict[str, int] = Field(default_factory=dict)
    top_templates: list[TemplateStats] = Field(default_factory=list)
    downloads_by_type: dict[str, int] = Field(default_factory=dict)


class UserAnalyticsResponse(BaseModel):
    """User-scoped analytics for Settings → Usage (also used for platform admin charts)."""

    period: StatsPeriod
    daily: list[DailyPoint]
    daily_uploads: list[DailyUploadPoint] = Field(default_factory=list)
    summary: AnalyticsSummary
    breakdown: AnalyticsBreakdown
