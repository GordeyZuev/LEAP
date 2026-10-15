"""Durable Celery dispatch intent for automatic platform uploads."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.dependencies import get_async_session_maker
from api.repositories.recording_repos import RecordingRepository
from database.models import OutputTargetModel, RecordingModel
from models.recording import TargetStatus


@dataclass(frozen=True)
class UploadDispatchIntent:
    target_id: int | None
    task_id: str | None
    reason: str | None = None


async def prepare_upload_dispatch(
    recording_id: int,
    user_id: str,
    platform: str,
    preset_id: int | None,
    metadata_override: dict | None,
) -> UploadDispatchIntent:
    """Save the intent before publishing; a launcher retry reuses its task id."""
    from api.tasks.upload import platform_to_target_type, upload_enqueue_skip_reason

    async with get_async_session_maker()() as session:
        repo = RecordingRepository(session)
        recording = await repo.get_by_id(recording_id, user_id)
        if recording is None:
            return UploadDispatchIntent(None, None, "Recording not found")
        target = await repo.get_or_create_output_target(recording, platform_to_target_type(platform), preset_id)
        await session.refresh(target, with_for_update=True)
        # Once an external upload has started, its outcome can be unknown after
        # a worker loss. Never create another automatic dispatch in that state.
        if target.status == TargetStatus.UPLOADING:
            return UploadDispatchIntent(target.id, target.dispatch_task_id, "Upload outcome needs review")
        if target.status == TargetStatus.FAILED or target.failed:
            return UploadDispatchIntent(
                target.id, target.dispatch_task_id, "Previous upload failed; review before retry"
            )
        reason = upload_enqueue_skip_reason(target)
        if reason:
            return UploadDispatchIntent(target.id, None, reason)
        if (
            target.status == TargetStatus.NOT_UPLOADED
            and target.dispatch_task_id
            and not target.failed
            and target.dispatch_finished_at is None
        ):
            if target.dispatch_published_at is not None:
                return UploadDispatchIntent(target.id, target.dispatch_task_id, "Already queued")
            return UploadDispatchIntent(target.id, target.dispatch_task_id)

        target.dispatch_task_id = str(uuid.uuid4())
        target.dispatch_platform = platform
        target.preset_id = preset_id
        target.dispatch_metadata_override = metadata_override
        target.dispatch_requested_at = datetime.now(UTC)
        target.dispatch_published_at = None
        target.dispatch_finished_at = None
        target.failed = False
        target.status = TargetStatus.NOT_UPLOADED
        await session.commit()
        return UploadDispatchIntent(target.id, target.dispatch_task_id)


async def publish_upload_dispatch(target_id: int, task_id: str) -> bool:
    """Re-publishing the same intent is safe for the output-row claim in the consumer."""
    from api.tasks.upload import upload_recording_to_platform

    async with get_async_session_maker()() as session:
        target = await session.get(OutputTargetModel, target_id)
        if (
            target is None
            or target.dispatch_task_id != task_id
            or target.dispatch_finished_at is not None
            or target.status != TargetStatus.NOT_UPLOADED
        ):
            return False
        user_id = await session.scalar(select(RecordingModel.user_id).where(RecordingModel.id == target.recording_id))
        if user_id is None:
            return False
        args = (
            target.recording_id,
            user_id,
            target.dispatch_platform,
            target.preset_id,
            None,
            target.dispatch_metadata_override,
            task_id,
        )

    await asyncio.to_thread(upload_recording_to_platform.apply_async, args=args, task_id=task_id)
    async with get_async_session_maker()() as session:
        target = await session.get(OutputTargetModel, target_id, with_for_update=True)
        if target is not None and target.dispatch_task_id == task_id:
            now = datetime.now(UTC)
            target.dispatch_published_at = now
            target.dispatch_requested_at = now
            await session.commit()
    return True


async def finish_upload_dispatch(recording_id: int, user_id: str, platform: str, task_id: str, result: dict) -> None:
    """Record a completed or terminally skipped upload so recovery stops publishing it."""
    from api.tasks.upload import platform_to_target_type

    if result.get("reason") == "Upload in progress":
        return
    async with get_async_session_maker()() as session:
        target = await session.scalar(
            select(OutputTargetModel)
            .join(RecordingModel, RecordingModel.id == OutputTargetModel.recording_id)
            .where(
                OutputTargetModel.recording_id == recording_id,
                RecordingModel.user_id == user_id,
                OutputTargetModel.target_type == platform_to_target_type(platform),
            )
            .with_for_update()
        )
        if target is None or target.dispatch_task_id != task_id:
            return
        target.dispatch_finished_at = datetime.now(UTC)
        if result.get("status") == "failed" or result.get("success") is False:
            from api.helpers.status_manager import update_aggregate_status

            target.status = TargetStatus.FAILED
            target.failed = True
            target.failed_at = target.dispatch_finished_at
            target.failed_reason = str(result.get("reason") or result.get("error") or "Upload failed")[:1000]
            recording = await session.scalar(
                select(RecordingModel)
                .options(selectinload(RecordingModel.outputs), selectinload(RecordingModel.processing_stages))
                .where(RecordingModel.id == recording_id, RecordingModel.user_id == user_id)
            )
            if recording is not None:
                update_aggregate_status(recording)
        await session.commit()
