"""User usage statistics service."""

from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.user.stats import StatsPeriod, TemplateStats, UserStatsResponse
from config.settings import get_settings
from database.models import RecordingModel
from database.template_models import RecordingTemplateModel
from file_storage.path_builder import StoragePathBuilder
from logger import get_logger
from models.recording import ProcessingStatus

logger = get_logger()


class StatsService:
    """Compute user usage statistics from recordings and disk."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_stats(
        self,
        user_id: str,
        user_slug: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> UserStatsResponse:
        """Aggregate recording stats for user, optionally filtered by date range."""
        base_filter = [
            RecordingModel.user_id == user_id,
            RecordingModel.deleted.is_(False),
        ]

        if from_date:
            base_filter.append(RecordingModel.created_at >= datetime.combine(from_date, time.min))
        if to_date:
            base_filter.append(RecordingModel.created_at <= datetime.combine(to_date, time.max))

        recordings_total = await self._count_recordings(base_filter)
        by_status = await self._count_by_status(base_filter)
        by_template = await self._count_ready_by_template(base_filter)
        transcription_seconds = await self._sum_transcription_seconds(base_filter)
        storage_bytes = self._calc_storage_bytes(user_slug)

        period = None
        if from_date or to_date:
            period = StatsPeriod(**{"from": from_date or date.min, "to": to_date or date.today()})

        return UserStatsResponse(
            period=period,
            recordings_total=recordings_total,
            recordings_by_status=by_status,
            recordings_ready_by_template=by_template,
            transcription_total_seconds=round(transcription_seconds, 2),
            storage_bytes=storage_bytes,
            storage_gb=round(storage_bytes / (1024**3), 3),
        )

    async def _count_recordings(self, filters: list) -> int:
        result = await self.session.scalar(select(func.count(RecordingModel.id)).where(*filters))
        return result or 0

    async def _count_by_status(self, filters: list) -> dict[str, int]:
        rows = await self.session.execute(
            select(RecordingModel.status, func.count(RecordingModel.id)).where(*filters).group_by(RecordingModel.status)
        )
        return {str(row[0]): row[1] for row in rows.all()}

    async def _count_ready_by_template(self, filters: list) -> list[TemplateStats]:
        ready_filters = [
            *filters,
            RecordingModel.status == ProcessingStatus.READY,
            RecordingModel.template_id.isnot(None),
        ]
        rows = await self.session.execute(
            select(
                RecordingModel.template_id,
                RecordingTemplateModel.name,
                func.count(RecordingModel.id),
            )
            .outerjoin(RecordingTemplateModel, RecordingModel.template_id == RecordingTemplateModel.id)
            .where(*ready_filters)
            .group_by(RecordingModel.template_id, RecordingTemplateModel.name)
        )
        return [TemplateStats(template_id=row[0], template_name=row[1], count=row[2]) for row in rows.all()]

    async def _sum_transcription_seconds(self, filters: list) -> float:
        """Sum final_duration (seconds) for recordings that have been transcribed."""
        result = await self.session.scalar(
            select(func.sum(RecordingModel.final_duration)).where(
                *filters,
                RecordingModel.final_duration.isnot(None),
            )
        )
        return float(result) if result else 0.0

    @staticmethod
    def _calc_storage_bytes(user_slug: int) -> int:
        settings = get_settings()
        builder = StoragePathBuilder(settings.storage.local_path)
        return builder.calc_user_storage_bytes(user_slug)
