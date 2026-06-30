"""Repository for usage_events (immutable action log)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.auth_models import UsageEventModel


class UsageEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: str,
        event_type: str,
        *,
        recording_id: int | None = None,
        duration_seconds: float | None = None,
        bytes_delta: int | None = None,
        metadata: dict | None = None,
    ) -> UsageEventModel:
        event = UsageEventModel(
            user_id=user_id,
            event_type=event_type,
            recording_id=recording_id,
            duration_seconds=duration_seconds,
            bytes_delta=bytes_delta,
            event_metadata=metadata,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_user(
        self,
        user_id: str,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageEventModel]:
        q = select(UsageEventModel).where(UsageEventModel.user_id == user_id)
        if from_dt:
            q = q.where(UsageEventModel.created_at >= from_dt)
        if to_dt:
            q = q.where(UsageEventModel.created_at <= to_dt)
        if event_type:
            q = q.where(UsageEventModel.event_type == event_type)
        q = q.order_by(UsageEventModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageEventModel]:
        q = select(UsageEventModel)
        if from_dt:
            q = q.where(UsageEventModel.created_at >= from_dt)
        if to_dt:
            q = q.where(UsageEventModel.created_at <= to_dt)
        if event_type:
            q = q.where(UsageEventModel.event_type == event_type)
        q = q.order_by(UsageEventModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())
