"""Async recording repository with multi-tenancy"""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import OutputTargetModel, RecordingModel, SourceMetadataModel
from logger import get_logger
from models.recording import ProcessingStatus, SourceType, TargetStatus

logger = get_logger()


class RecordingRepository:
    """Repository for working with recordings."""

    def __init__(self, session: AsyncSession):
        """
        Initialize repository.

        Args:
            session: Async database session
        """
        self.session = session

    async def get_by_id(
        self, recording_id: int, user_id: str, include_deleted: bool = False
    ) -> RecordingModel | None:
        """
        Get recording by ID with user ownership check.

        Args:
            recording_id: Recording ID
            user_id: User ID
            include_deleted: Include deleted recordings

        Returns:
            Recording or None
        """
        query = (
            select(RecordingModel)
            .options(
                selectinload(RecordingModel.source).selectinload(SourceMetadataModel.input_source),
                selectinload(RecordingModel.outputs).selectinload(OutputTargetModel.preset),
                selectinload(RecordingModel.processing_stages),
                selectinload(RecordingModel.input_source),
            )
            .where(
                RecordingModel.id == recording_id,
                RecordingModel.user_id == user_id,
            )
        )

        if not include_deleted:
            query = query.where(RecordingModel.deleted == False)  # noqa: E712

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_ids(
        self, recording_ids: list[int], user_id: str, include_deleted: bool = False
    ) -> dict[int, RecordingModel]:
        """
        Get multiple recordings by IDs (batch load to avoid N+1).

        Args:
            recording_ids: List of recording IDs
            user_id: User ID
            include_deleted: Include deleted recordings

        Returns:
            Dict mapping recording_id to RecordingModel
        """
        if not recording_ids:
            return {}

        query = (
            select(RecordingModel)
            .options(
                selectinload(RecordingModel.source).selectinload(SourceMetadataModel.input_source),
                selectinload(RecordingModel.outputs).selectinload(OutputTargetModel.preset),
                selectinload(RecordingModel.processing_stages),
                selectinload(RecordingModel.input_source),
            )
            .where(
                RecordingModel.id.in_(recording_ids),
                RecordingModel.user_id == user_id,
            )
        )

        if not include_deleted:
            query = query.where(RecordingModel.deleted == False)  # noqa: E712

        result = await self.session.execute(query)
        recordings = result.scalars().all()

        return {rec.id: rec for rec in recordings}

    async def list_by_user(
        self,
        user_id: str,
        status: ProcessingStatus | None = None,
        input_source_id: int | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecordingModel]:
        """
        Get list of recordings for user.

        Args:
            user_id: User ID
            status: Filter by status
            input_source_id: Filter by input source
            include_deleted: Include deleted recordings
            limit: Limit of recordings
            offset: Offset

        Returns:
            List of recordings
        """
        query = (
            select(RecordingModel)
            .options(
                selectinload(RecordingModel.source).selectinload(SourceMetadataModel.input_source),
                selectinload(RecordingModel.outputs).selectinload(OutputTargetModel.preset),
                selectinload(RecordingModel.processing_stages),
                selectinload(RecordingModel.input_source),
            )
            .where(RecordingModel.user_id == user_id)
            .order_by(RecordingModel.start_time.desc())
            .limit(limit)
            .offset(offset)
        )

        if not include_deleted:
            query = query.where(RecordingModel.deleted == False)  # noqa: E712

        if status:
            query = query.where(RecordingModel.status == status)

        if input_source_id:
            query = query.where(RecordingModel.input_source_id == input_source_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        user_id: str,
        input_source_id: int | None,
        display_name: str,
        start_time: datetime,
        duration: int,
        source_type: SourceType,
        source_key: str,
        source_metadata: dict[str, Any] | None = None,
        user_config: dict | None = None,
        **kwargs,
    ) -> RecordingModel:
        """
        Create new recording.

        Args:
            user_id: User ID
            input_source_id: Input source ID
            display_name: Recording name
            start_time: Start time
            duration: Duration
            source_type: Source type
            source_key: Source key
            source_metadata: Source metadata
            user_config: User configuration for retention settings
            **kwargs: Additional fields

        Returns:
            Created recording
        """
        # Get retention settings
        retention = user_config.get("retention", {}) if isinstance(user_config, dict) else {}
        auto_expire_days = retention.get("auto_expire_days", 90)

        # Set expire_at (can be overridden by Zoom API deleted_at via kwargs)
        expire_at = kwargs.get("expire_at")
        if expire_at is None and auto_expire_days:
            expire_at = datetime.now(UTC) + timedelta(days=auto_expire_days)

        recording = RecordingModel(
            user_id=user_id,
            input_source_id=input_source_id,
            display_name=display_name,
            start_time=start_time,
            duration=duration,
            status=kwargs.get("status", ProcessingStatus.INITIALIZED),
            is_mapped=kwargs.get("is_mapped", False),
            video_file_size=kwargs.get("video_file_size"),
            expire_at=expire_at,
            delete_state="active",
            local_video_path=kwargs.get("local_video_path"),
            processed_video_path=kwargs.get("processed_video_path"),
        )

        self.session.add(recording)
        await self.session.flush()

        # Create source metadata
        source = SourceMetadataModel(
            recording_id=recording.id,
            user_id=user_id,
            input_source_id=input_source_id,
            source_type=source_type,
            source_key=source_key,
            meta=source_metadata or {},
        )

        self.session.add(source)
        await self.session.flush()

        logger.info(f"Created recording {recording.id} for user {user_id} from source {input_source_id}")

        return recording

    async def update(
        self,
        recording: RecordingModel,
        **fields,
    ) -> RecordingModel:
        """
        Update recording.

        Args:
            recording: Recording to update
            **fields: Fields to update

        Returns:
            Updated recording
        """
        for field, value in fields.items():
            if hasattr(recording, field):
                setattr(recording, field, value)

        recording.updated_at = datetime.now(UTC)
        await self.session.flush()

        logger.debug(f"Updated recording {recording.id}")
        return recording


    async def get_or_create_output_target(
        self,
        recording: RecordingModel,
        target_type: str,
        preset_id: int | None = None,
    ) -> OutputTargetModel:
        """
        Get or create output_target.

        Args:
            recording: Recording
            target_type: Target type
            preset_id: ID output preset

        Returns:
            OutputTargetModel
        """
        # Find existing output_target via explicit DB query
        # (don't rely on recording.outputs - it may not be loaded)
        stmt = select(OutputTargetModel).where(
            OutputTargetModel.recording_id == recording.id,
            OutputTargetModel.target_type == target_type,
        )
        result = await self.session.execute(stmt)
        existing_output = result.scalar_one_or_none()

        if existing_output:
            logger.debug(f"Found existing output_target for recording {recording.id} to {target_type}")
            return existing_output

        # Create new
        output = OutputTargetModel(
            recording_id=recording.id,
            user_id=recording.user_id,
            preset_id=preset_id,
            target_type=target_type,
            status=TargetStatus.NOT_UPLOADED,
            target_meta={},
        )

        self.session.add(output)
        await self.session.flush()

        logger.info(f"Created output_target for recording {recording.id} to {target_type}")
        return output

    async def mark_output_uploading(
        self,
        output_target: OutputTargetModel,
    ) -> None:
        """
        Mark output_target as uploading and update aggregate status.
        """
        from api.helpers.status_manager import update_aggregate_status

        output_target.status = TargetStatus.UPLOADING
        output_target.failed = False
        output_target.updated_at = datetime.now(UTC)
        await self.session.flush()

        # Refresh recording to ensure outputs are loaded
        recording = output_target.recording
        await self.session.refresh(recording, ["outputs"])

        # Update aggregate recording status (PROCESSED → UPLOADING)
        update_aggregate_status(recording)

        logger.debug(f"Marked output_target {output_target.id} as UPLOADING, recording {recording.id} status: {recording.status}")

    async def mark_output_failed(
        self,
        output_target: OutputTargetModel,
        error_message: str,
    ) -> None:
        """
        Mark output_target as failed and update aggregate status.

        Args:
            output_target: Output target
            error_message: Error message
        """
        from api.helpers.status_manager import update_aggregate_status

        output_target.status = TargetStatus.FAILED
        output_target.failed = True
        output_target.failed_at = datetime.now(UTC)
        output_target.failed_reason = error_message[:1000]  # Length limit
        output_target.retry_count += 1
        output_target.updated_at = datetime.now(UTC)
        await self.session.flush()

        # Refresh recording to ensure outputs are loaded
        recording = output_target.recording
        await self.session.refresh(recording, ["outputs"])

        # Update aggregate recording status (may revert from UPLOADING to PROCESSED)
        update_aggregate_status(recording)

        logger.warning(f"Marked output_target {output_target.id} as FAILED: {error_message[:100]}, recording {recording.id} status: {recording.status}")

    async def save_upload_result(
        self,
        recording: RecordingModel,
        target_type: str,
        preset_id: int | None,
        video_id: str,
        video_url: str,
        target_meta: dict[str, Any] | None = None,
    ) -> OutputTargetModel:
        """
        Save upload results and update aggregate status.

        Args:
            recording: Recording
            target_type: Target type
            preset_id: ID output preset
            video_id: ID video on platform
            video_url: Video URL
            target_meta: Target metadata

        Returns:
            OutputTarget
        """
        from api.helpers.status_manager import update_aggregate_status

        # Check if there is already output for this target_type (explicit DB query)
        stmt = select(OutputTargetModel).where(
            OutputTargetModel.recording_id == recording.id,
            OutputTargetModel.target_type == target_type,
        )
        result = await self.session.execute(stmt)
        existing_output = result.scalar_one_or_none()

        if existing_output:
            # Update existing
            existing_output.status = TargetStatus.UPLOADED
            existing_output.preset_id = preset_id
            existing_output.target_meta = {
                **(existing_output.target_meta or {}),
                "video_id": video_id,
                "video_url": video_url,
                **(target_meta or {}),
            }
            existing_output.uploaded_at = datetime.now(UTC)
            existing_output.failed = False
            existing_output.updated_at = datetime.now(UTC)
            await self.session.flush()

            logger.info(f"Updated upload result for recording {recording.id} to {target_type}")
            output = existing_output
        else:
            # Create new
            output = OutputTargetModel(
                recording_id=recording.id,
                user_id=recording.user_id,
                preset_id=preset_id,
                target_type=target_type,
                status=TargetStatus.UPLOADED,
                target_meta={
                    "video_id": video_id,
                    "video_url": video_url,
                    **(target_meta or {}),
                },
                uploaded_at=datetime.now(UTC),
            )

            self.session.add(output)
            await self.session.flush()

            logger.info(f"Created upload result for recording {recording.id} to {target_type}")

        # Refresh recording to ensure outputs are loaded
        await self.session.refresh(recording, ["outputs"])

        # Update aggregate recording status (UPLOADING → READY or PROCESSED → READY)
        update_aggregate_status(recording)
        logger.info(f"Updated recording {recording.id} aggregate status to {recording.status}")

        return output

    async def find_by_source_key(
        self,
        user_id: str,
        source_type: SourceType,
        source_key: str,
        start_time: datetime,
    ) -> RecordingModel | None:
        """
        Find recording by source_key, source_type and start_time.
        """
        query = (
            select(RecordingModel)
            .options(
                selectinload(RecordingModel.source).selectinload(SourceMetadataModel.input_source),
                selectinload(RecordingModel.outputs).selectinload(OutputTargetModel.preset),
                selectinload(RecordingModel.processing_stages),
                selectinload(RecordingModel.input_source),
            )
            .join(SourceMetadataModel)
            .where(
                RecordingModel.user_id == user_id,
                SourceMetadataModel.source_type == source_type,
                SourceMetadataModel.source_key == source_key,
                RecordingModel.start_time == start_time,
            )
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        user_id: str,
        input_source_id: int | None,
        display_name: str,
        start_time: datetime,
        duration: int,
        source_type: SourceType,
        source_key: str,
        source_metadata: dict[str, Any] | None = None,
        user_config: dict | None = None,
        **kwargs,
    ) -> tuple[RecordingModel, bool]:
        """
        Create or update recording (upsert logic).

        Args:
            user_id: User ID
            input_source_id: Input source ID
            display_name: Recording name
            start_time: Start time
            duration: Duration
            source_type: Source type
            source_key: Source key
            source_metadata: Source metadata
            user_config: User configuration for retention settings
            **kwargs: Additional fields

        Returns:
            Tuple (recording, was_created)
        """
        # Check existing recording
        existing = await self.find_by_source_key(user_id, source_type, source_key, start_time)

        if existing:
            # Don't update deleted recordings (user deleted manually)
            if existing.deleted:
                logger.info(f"Skipped updating recording {existing.id} - marked as deleted")
                return existing, False

            # Update existing recording, but only if status is not UPLOADED
            if existing.status != ProcessingStatus.UPLOADED:
                existing.display_name = display_name
                existing.duration = duration
                existing.video_file_size = kwargs.get("video_file_size", existing.video_file_size)

                # Check if Zoom is still processing
                zoom_processing_incomplete = kwargs.get("zoom_processing_incomplete", False)

                # Update is_mapped and template_id (but don't change status if PENDING_SOURCE)
                if "is_mapped" in kwargs:
                    old_is_mapped = existing.is_mapped
                    existing.is_mapped = kwargs["is_mapped"]

                    # Update status only if not PENDING_SOURCE and in initial states
                    if existing.status != ProcessingStatus.PENDING_SOURCE and existing.status in [
                        ProcessingStatus.INITIALIZED,
                        ProcessingStatus.SKIPPED,
                    ]:
                        # Check if this is resync from PENDING_SOURCE (Zoom finished processing)
                        if old_is_mapped != existing.is_mapped:
                            existing.status = (
                                ProcessingStatus.INITIALIZED if existing.is_mapped else ProcessingStatus.SKIPPED
                            )

                # Handle status transition from PENDING_SOURCE when Zoom finishes processing
                if existing.status == ProcessingStatus.PENDING_SOURCE and not zoom_processing_incomplete:
                    # Zoom finished processing - recheck blank and update status
                    is_blank = kwargs.get("blank_record", False)
                    if is_blank:
                        existing.status = ProcessingStatus.SKIPPED
                    elif existing.is_mapped:
                        existing.status = ProcessingStatus.INITIALIZED
                    else:
                        existing.status = ProcessingStatus.SKIPPED
                    logger.info(
                        f"Recording {existing.id} processing completed on Zoom side: "
                        f"PENDING_SOURCE → {existing.status}"
                    )

                # Update template_id if passed
                if "template_id" in kwargs:
                    existing.template_id = kwargs["template_id"]

                # Update blank_record if passed
                if "blank_record" in kwargs:
                    existing.blank_record = kwargs["blank_record"]

                # Update source metadata
                if existing.source:
                    existing_meta = existing.source.meta if isinstance(existing.source.meta, dict) else {}
                    merged_meta = dict(existing_meta)
                    merged_meta.update(source_metadata or {})
                    existing.source.meta = merged_meta

                existing.updated_at = datetime.now(UTC)

                logger.info(f"Updated existing recording {existing.id} for user {user_id} (status={existing.status})")

                await self.session.flush()
                return existing, False
            # Recording already uploaded, don't update
            logger.info(f"Skipped updating recording {existing.id} - already uploaded")
            return existing, False
        # Create new recording
        is_mapped = kwargs.get("is_mapped", False)
        is_blank = kwargs.get("blank_record", False)
        zoom_processing_incomplete = kwargs.get("zoom_processing_incomplete", False)

        # Determine initial status based on Zoom processing state
        if zoom_processing_incomplete:
            status = ProcessingStatus.PENDING_SOURCE
        elif is_blank:
            status = ProcessingStatus.SKIPPED
        elif is_mapped:
            status = ProcessingStatus.INITIALIZED
        else:
            status = ProcessingStatus.SKIPPED

        # Get retention settings
        retention = user_config.get("retention", {}) if isinstance(user_config, dict) else {}
        auto_expire_days = retention.get("auto_expire_days", 90)

        # Set expire_at (can be overridden by Zoom API deleted_at via kwargs)
        expire_at = kwargs.get("expire_at")
        if expire_at is None and auto_expire_days:
            expire_at = datetime.now(UTC) + timedelta(days=auto_expire_days)

        recording = RecordingModel(
            user_id=user_id,
            input_source_id=input_source_id,
            template_id=kwargs.get("template_id"),
            display_name=display_name,
            start_time=start_time,
            duration=duration,
            status=status,
            is_mapped=is_mapped,
            blank_record=kwargs.get("blank_record", False),
            video_file_size=kwargs.get("video_file_size"),
            expire_at=expire_at,
            delete_state="active",
            local_video_path=kwargs.get("local_video_path"),
            processed_video_path=kwargs.get("processed_video_path"),
        )

        self.session.add(recording)
        await self.session.flush()

        # Create source metadata
        source = SourceMetadataModel(
            recording_id=recording.id,
            user_id=user_id,
            input_source_id=input_source_id,
            source_type=source_type,
            source_key=source_key,
            meta=source_metadata or {},
        )

        self.session.add(source)
        await self.session.flush()

        logger.info(f"Created new recording {recording.id} for user {user_id} (is_mapped={is_mapped}, status={status})")

        return recording, True

    async def soft_delete(self, recording: RecordingModel, user_config: dict) -> None:
        """
        Soft delete recording - mark as manually deleted by user.

        Sets delete_state to "soft", schedules file cleanup and hard delete based on user retention.

        Args:
            recording: Recording to soft delete
            user_config: User configuration containing retention settings
        """
        now = datetime.now(UTC)
        recording.deleted = True
        recording.delete_state = "soft"
        recording.deletion_reason = "manual"
        recording.deleted_at = now
        recording.expire_at = None  # Cancel auto-expiration
        recording.updated_at = now

        # Schedule both cleanup dates immediately (both in future)
        retention = user_config.get("retention", {})
        soft_days = retention.get("soft_delete_days", 3)
        hard_days = retention.get("hard_delete_days", 30)
        recording.soft_deleted_at = now + timedelta(days=soft_days)  # When files will be deleted
        recording.hard_delete_at = now + timedelta(days=soft_days + hard_days)  # When DB record deleted

        await self.session.flush()

        logger.info(
            f"Soft deleted recording {recording.id} (manual), "
            f"files cleanup at {recording.soft_deleted_at}, hard delete at {recording.hard_delete_at}"
        )

    async def auto_expire(self, recording: RecordingModel, user_config: dict) -> None:
        """
        Mark recording as auto-expired (expire_at reached).

        Sets delete_state to "soft", schedules file cleanup and hard delete based on user retention.

        Args:
            recording: Recording to expire
            user_config: User configuration containing retention settings
        """
        now = datetime.now(UTC)
        recording.deleted = True
        recording.delete_state = "soft"
        recording.deletion_reason = "expired"
        recording.deleted_at = now
        recording.expire_at = None  # Already expired
        recording.updated_at = now

        # Schedule both cleanup dates immediately (both in future)
        retention = user_config.get("retention", {})
        soft_days = retention.get("soft_delete_days", 3)
        hard_days = retention.get("hard_delete_days", 30)
        recording.soft_deleted_at = now + timedelta(days=soft_days)  # When files will be deleted
        recording.hard_delete_at = now + timedelta(days=soft_days + hard_days)  # When DB record deleted

        await self.session.flush()

        logger.info(
            f"Auto-expired recording {recording.id}, "
            f"files cleanup at {recording.soft_deleted_at}, hard delete at {recording.hard_delete_at}"
        )

    async def restore(self, recording: RecordingModel, user_config: dict) -> None:
        """
        Restore soft deleted recording (only if files still present).

        Clears deletion info and sets new expire_at from user config.

        Args:
            recording: Recording to restore
            user_config: User configuration containing retention settings

        Raises:
            ValueError: If files already deleted (delete_state != "soft")
        """
        if recording.delete_state != "soft":
            raise ValueError("Cannot restore: files already deleted")

        # Clear deletion info
        recording.deleted = False
        recording.delete_state = "active"
        recording.deletion_reason = None
        recording.deleted_at = None
        recording.hard_delete_at = None
        recording.soft_deleted_at = None

        # Set new expire_at from user config
        retention = user_config.get("retention", {})
        auto_expire_days = retention.get("auto_expire_days", 90)
        if auto_expire_days:
            recording.expire_at = datetime.now(UTC) + timedelta(days=auto_expire_days)

        recording.updated_at = datetime.now(UTC)

        await self.session.flush()

        logger.info(f"Restored recording {recording.id}, will expire at {recording.expire_at}")

    async def cleanup_recording_files(self, recording: RecordingModel) -> int:
        """
        Delete large files (videos, audio) for recording.
        Keeps: master.json, topics.json (transcription_dir), DB metadata.

        Used by maintenance tasks and hard delete.

        Args:
            recording: Recording to clean up

        Returns:
            Total bytes freed
        """
        # CRITICAL: Check state before cleanup to prevent race conditions
        if recording.delete_state != "soft":
            logger.warning(
                f"Skipped cleanup for recording {recording.id}: "
                f"delete_state={recording.delete_state} (expected 'soft')"
            )
            return 0

        total_bytes = 0

        # Delete original video
        if recording.local_video_path and Path(recording.local_video_path).exists():
            try:
                size = Path(recording.local_video_path).stat().st_size
                Path(recording.local_video_path).unlink()
                total_bytes += size
                logger.debug(f"Deleted local_video_path: {recording.local_video_path} ({size} bytes)")
            except Exception as e:
                logger.warning(f"Failed to delete local_video: path={recording.local_video_path} | error={e}")

        # Delete processed video
        if recording.processed_video_path and Path(recording.processed_video_path).exists():
            try:
                size = Path(recording.processed_video_path).stat().st_size
                Path(recording.processed_video_path).unlink()
                total_bytes += size
                logger.debug(f"Deleted processed_video_path: {recording.processed_video_path} ({size} bytes)")
            except Exception as e:
                logger.warning(f"Failed to delete processed_video: path={recording.processed_video_path} | error={e}")

        # Delete audio
        if recording.processed_audio_path and Path(recording.processed_audio_path).exists():
            try:
                size = Path(recording.processed_audio_path).stat().st_size
                Path(recording.processed_audio_path).unlink()
                total_bytes += size
                logger.debug(f"Deleted processed_audio_path: {recording.processed_audio_path} ({size} bytes)")
            except Exception as e:
                logger.warning(f"Failed to delete audio: path={recording.processed_audio_path} | error={e}")

        # Clear paths in DB
        recording.local_video_path = None
        recording.processed_video_path = None
        recording.processed_audio_path = None

        # Update state (soft_deleted_at already set, just change state)
        recording.delete_state = "hard"
        recording.updated_at = datetime.now(UTC)

        return total_bytes

    async def delete(self, recording: RecordingModel) -> None:
        """
        Hard delete recording - complete removal from DB.

        Deletes all files (if not cleaned yet) and removes DB record.
        Used by hard delete maintenance task and account deletion.

        Args:
            recording: Recording to delete
        """
        total_bytes = 0

        # Delete large files if not cleaned yet
        if recording.delete_state != "hard":
            total_bytes += await self.cleanup_recording_files(recording)

        # Delete transcription directory (master.json, topics.json, etc)
        if recording.transcription_dir and Path(recording.transcription_dir).exists():
            try:
                dir_path = Path(recording.transcription_dir)
                dir_size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
                shutil.rmtree(dir_path)
                total_bytes += dir_size
                logger.debug(f"Deleted transcription_dir: {recording.transcription_dir} ({dir_size} bytes)")
            except Exception as e:
                logger.warning(f"Failed to delete transcription_dir: path={recording.transcription_dir} | error={e}")

        # Delete from DB
        await self.session.delete(recording)
        await self.session.flush()

        # TODO: Update quota (placeholder for now)
        # if total_bytes > 0 and recording.user_id:
        #     quota_service = QuotaService(self.session)
        #     await quota_service.track_storage_removed(recording.user_id, total_bytes)

        logger.info(f"Hard deleted recording {recording.id}, freed {total_bytes} bytes")
