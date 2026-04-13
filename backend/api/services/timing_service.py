"""Centralized timing writes for the stage_timings audit table."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import StageTimingModel
from logger import get_logger

logger = get_logger(__name__)


class TimingService:
    """Write timing events to stage_timings (append-only audit/analytics).

    All stage/substep start/complete/fail operations go through this service
    to keep task code DRY and ensure consistent timing writes.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, timing_id: int) -> StageTimingModel | None:
        """Retrieve a timing row by ID (for cross-session workflows)."""
        result = await self.session.execute(select(StageTimingModel).where(StageTimingModel.id == timing_id))
        return result.scalar_one_or_none()

    async def start_stage(
        self,
        recording_id: int,
        user_id: str | None,
        stage_type: str,
        attempt: int = 1,
        meta: dict[str, Any] | None = None,
    ) -> StageTimingModel:
        """Record stage start. Returns the timing row for later completion."""
        timing = StageTimingModel(
            recording_id=recording_id,
            user_id=user_id,
            stage_type=stage_type,
            attempt=attempt,
            started_at=datetime.now(UTC),
            status="IN_PROGRESS",
            meta=meta,
        )
        self.session.add(timing)
        await self.session.flush()
        logger.debug(f"Timing started: recording={recording_id} stage={stage_type} attempt={attempt}")
        return timing

    async def complete_stage(
        self,
        timing: StageTimingModel,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Record stage completion with computed duration."""
        now = datetime.now(UTC)
        timing.completed_at = now
        timing.duration_seconds = (now - timing.started_at).total_seconds()
        timing.status = "COMPLETED"
        if meta:
            timing.meta = {**(timing.meta or {}), **meta}
        logger.debug(
            f"Timing completed: recording={timing.recording_id} "
            f"stage={timing.stage_type} duration={timing.duration_seconds:.1f}s"
        )

    async def fail_stage(
        self,
        timing: StageTimingModel,
        error: str,
    ) -> None:
        """Record stage failure with duration up to failure point."""
        now = datetime.now(UTC)
        timing.completed_at = now
        timing.duration_seconds = (now - timing.started_at).total_seconds()
        timing.status = "FAILED"
        timing.error_message = error[:1000]
        logger.debug(
            f"Timing failed: recording={timing.recording_id} "
            f"stage={timing.stage_type} duration={timing.duration_seconds:.1f}s error={error[:100]}"
        )

    async def start_substep(
        self,
        recording_id: int,
        user_id: str | None,
        stage_type: str,
        substep: str,
        attempt: int = 1,
    ) -> StageTimingModel:
        """Record substep start within a stage."""
        timing = StageTimingModel(
            recording_id=recording_id,
            user_id=user_id,
            stage_type=stage_type,
            substep=substep,
            attempt=attempt,
            started_at=datetime.now(UTC),
            status="IN_PROGRESS",
        )
        self.session.add(timing)
        await self.session.flush()
        return timing

    async def complete_substep(
        self,
        timing: StageTimingModel,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Record substep completion."""
        await self.complete_stage(timing, meta=meta)

    async def fail_substep(
        self,
        timing: StageTimingModel,
        error: str,
    ) -> None:
        """Record substep failure."""
        await self.fail_stage(timing, error)
