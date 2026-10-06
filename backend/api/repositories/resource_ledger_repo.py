"""Persistence for provider spend rows."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.auth_models import ResourceLedgerModel


class ResourceLedgerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_job_id(self, provider_job_id: str) -> ResourceLedgerModel | None:
        result = await self.session.execute(
            select(ResourceLedgerModel).where(ResourceLedgerModel.provider_job_id == provider_job_id)
        )
        return result.scalar_one_or_none()

    async def open_transcription_job_id(self, recording_id: int) -> str | None:
        """Latest AssemblyAI job that was submitted and not yet closed for this recording."""
        result = await self.session.execute(
            select(ResourceLedgerModel.provider_job_id)
            .where(
                ResourceLedgerModel.recording_id == recording_id,
                ResourceLedgerModel.provider == "assemblyai",
                ResourceLedgerModel.operation == "transcribe",
                ResourceLedgerModel.status == "submitted",
                ResourceLedgerModel.provider_job_id.is_not(None),
            )
            .order_by(ResourceLedgerModel.occurred_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def submitted_transcriptions(self, older_than: datetime) -> list[ResourceLedgerModel]:
        result = await self.session.execute(
            select(ResourceLedgerModel).where(
                ResourceLedgerModel.provider == "assemblyai",
                ResourceLedgerModel.operation == "transcribe",
                ResourceLedgerModel.status == "submitted",
                ResourceLedgerModel.provider_job_id.is_not(None),
                ResourceLedgerModel.occurred_at < older_than,
            )
        )
        return list(result.scalars().all())

    async def get_by_idempotency(self, key: str) -> ResourceLedgerModel | None:
        result = await self.session.execute(
            select(ResourceLedgerModel).where(ResourceLedgerModel.idempotency_key == key).limit(1)
        )
        return result.scalar_one_or_none()

    async def segment_end_watermark(self) -> datetime | None:
        """Latest historical estimate. Unattributed imports must be newer than this."""
        basis = ResourceLedgerModel.details["basis"].astext
        result = await self.session.execute(
            select(func.max(ResourceLedgerModel.occurred_at)).where(
                ResourceLedgerModel.provider == "assemblyai",
                ResourceLedgerModel.operation == "transcribe",
                basis == "segment_end",
            )
        )
        value = result.scalar_one_or_none()
        return value if isinstance(value, datetime) else None

    async def segment_end_by_recording(self) -> dict[int, datetime]:
        """Latest segment_end estimate per recording. A real transcript at or before it is already counted."""
        basis = ResourceLedgerModel.details["basis"].astext
        result = await self.session.execute(
            select(ResourceLedgerModel.recording_id, func.max(ResourceLedgerModel.occurred_at))
            .where(
                ResourceLedgerModel.provider == "assemblyai",
                ResourceLedgerModel.operation == "transcribe",
                ResourceLedgerModel.recording_id.is_not(None),
                basis == "segment_end",
            )
            .group_by(ResourceLedgerModel.recording_id)
        )
        estimates: dict[int, datetime] = {}
        for recording_id, occurred_at in result.all():
            if isinstance(recording_id, int) and isinstance(occurred_at, datetime):
                estimates[recording_id] = occurred_at
        return estimates

    async def existing_job_ids(self, job_ids: list[str]) -> set[str]:
        if not job_ids:
            return set()
        result = await self.session.execute(
            select(ResourceLedgerModel.provider_job_id).where(ResourceLedgerModel.provider_job_id.in_(job_ids))
        )
        return {job_id for job_id in result.scalars().all() if isinstance(job_id, str)}

    async def submitted_without_job_for_audio_url(self, audio_url: str) -> ResourceLedgerModel | None:
        audio = ResourceLedgerModel.details["audio_url"].astext
        result = await self.session.execute(
            select(ResourceLedgerModel)
            .where(
                ResourceLedgerModel.provider == "assemblyai",
                ResourceLedgerModel.operation == "transcribe",
                ResourceLedgerModel.status == "submitted",
                ResourceLedgerModel.provider_job_id.is_(None),
                audio == audio_url,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_idempotency_key(self, key: str) -> bool:
        result = await self.session.execute(
            select(ResourceLedgerModel.id).where(ResourceLedgerModel.idempotency_key == key).limit(1)
        )
        return result.scalar_one_or_none() is not None

    def add(self, row: ResourceLedgerModel) -> None:
        self.session.add(row)

    async def insert_ignore(self, values: dict) -> None:
        stmt = insert(ResourceLedgerModel).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"])
        await self.session.execute(stmt)
