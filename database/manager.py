from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import asyncpg
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from logger import get_logger
from models.recording import (
    MeetingRecording,
    OutputTarget,
    ProcessingStage,
    ProcessingStageStatus,
    ProcessingStageType,
    ProcessingStatus,
    SourceType,
    TargetStatus,
    TargetType,
    _normalize_enum,
)

from .config import DatabaseConfig
from .models import (
    Base,
    OutputTargetModel,
    ProcessingStageModel,
    RecordingModel,
    SourceMetadataModel,
)

logger = get_logger()


def _parse_start_time(start_time_str: str) -> datetime:
    """Parsing the start_time string to a datetime object (Zoom format: 2021-03-18T05:41:36Z)."""
    if not start_time_str:
        raise ValueError("start_time cannot be empty")

    try:
        if start_time_str.endswith("Z"):
            time_str = start_time_str[:-1] + "+00:00"
        else:
            time_str = start_time_str

        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt
    except Exception as e:
        logger.error(f"Error parsing start_time: value={start_time_str}", start_time_str=start_time_str, error=str(e))
        raise ValueError(f"Failed to parse start_time: {start_time_str}") from e


def _build_source_metadata_payload(recording: MeetingRecording) -> dict:
    """Builds the JSONB source metadata from the model."""
    meta = dict(recording.source_metadata or {})

    # Main Zoom fields
    zoom_fields = {
        "meeting_id": getattr(recording, "meeting_id", None),
        "account": getattr(recording, "account", None),
        "video_file_download_url": getattr(recording, "video_file_download_url", None),
        "download_access_token": getattr(recording, "download_access_token", None),
        "password": getattr(recording, "password", None),
        "recording_play_passcode": getattr(recording, "recording_play_passcode", None),
        "part_index": getattr(recording, "part_index", None),
        "total_visible_parts": getattr(recording, "total_visible_parts", None),
    }
    for key, value in zoom_fields.items():
        if value:
            meta[key] = value

    if recording.video_file_size is not None:
        meta["video_file_size"] = recording.video_file_size

    return meta


class DatabaseManager:
    """Manager for working with the database."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = create_async_engine(config.url, echo=False)
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def create_database_if_not_exists(self):
        """Create the database if it does not exist."""
        try:
            parsed = urlparse(self.config.url)

            conn = await asyncpg.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database="postgres",
            )

            result = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", self.config.database)

            if not result:
                await conn.execute(f'CREATE DATABASE "{self.config.database}"')
                logger.info(f"Database created: database={self.config.database}")

            await conn.close()

        except Exception as e:
            logger.error(f"Error creating database: database={self.config.database} | error={e}")
            raise

    async def recreate_database(self):
        """Full database recreation: deletion and creation again."""
        try:
            parsed = urlparse(self.config.url)

            try:
                await self.close()
            except Exception as e:
                logger.debug(f"Error closing connection (may not exist yet): {e}")

            conn = await asyncpg.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database="postgres",
            )

            db_exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", self.config.database)

            if db_exists:
                try:
                    await conn.execute(
                        """
                        SELECT pg_terminate_backend(pg_stat_activity.pid)
                        FROM pg_stat_activity
                        WHERE pg_stat_activity.datname = $1
                        AND pid <> pg_backend_pid()
                    """,
                        self.config.database,
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to terminate all connections: database={self.config.database}",
                        database=self.config.database,
                        error=str(e),
                    )

                db_name_quoted = self.config.database.replace('"', '""')
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name_quoted}"')
                logger.info(f"Database deleted: database={self.config.database}")

            db_name_quoted = self.config.database.replace('"', '""')
            await conn.execute(f'CREATE DATABASE "{db_name_quoted}"')
            logger.info(f"Database created: database={self.config.database}")

            await conn.close()

            self.engine = create_async_engine(self.config.url, echo=False)
            self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

            await self.create_tables()

            logger.info(f"Database fully recreated: database={self.config.database}")

        except Exception as e:
            logger.error(f"Error recreating database: database={self.config.database} | error={e}")
            raise

    async def create_tables(self):
        """Create tables in the database."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Tables created")
        except Exception as e:
            logger.error(f"Error creating tables: error={e}")
            raise

    async def save_recordings(self, recordings: list[MeetingRecording]) -> int:
        """Save recordings to the database."""
        if not recordings:
            return 0

        saved_count = 0
        async with self.async_session() as session:
            try:
                for recording in recordings:
                    try:
                        existing = await self._find_existing_recording(session, recording)
                        if existing:
                            await self._update_existing_recording(session, existing, recording)
                        else:
                            await self._create_new_recording(session, recording)
                        saved_count += 1
                    except IntegrityError as e:
                        logger.warning(
                            f"Recording already exists: recording={recording.display_name} | recording_id={recording.db_id} | error={e}"
                        )
                        await session.rollback()
                        continue
                    except Exception as e:
                        logger.error(
                            f"Error saving recording: recording={recording.display_name} | recording_id={recording.db_id} | error={e}"
                        )
                        await session.rollback()
                        continue

                await session.commit()
                logger.info(f"Saved recordings: {saved_count}/{len(recordings)}")
                return saved_count

            except Exception as e:
                await session.rollback()
                logger.error(f"Transaction error: error={e}")
                raise

    async def _find_existing_recording(
        self, session: AsyncSession, recording: MeetingRecording
    ) -> RecordingModel | None:
        """Search for an existing recording by source_type, source_key and start_time."""
        try:
            start_time = _parse_start_time(recording.start_time)
            source_type = _normalize_enum(recording.source_type, SourceType)
            stmt = (
                select(RecordingModel)
                .options(
                    selectinload(RecordingModel.source),
                    selectinload(RecordingModel.outputs),
                    selectinload(RecordingModel.processing_stages),
                )
                .join(SourceMetadataModel)
                .where(
                    SourceMetadataModel.source_type == source_type,
                    SourceMetadataModel.source_key == recording.source_key,
                    RecordingModel.start_time == start_time,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                f"Error searching for existing recording: source_type={recording.source_type} | source_key={recording.source_key} | error={e}"
            )
            return None

    async def _update_existing_recording(
        self, session: AsyncSession, existing: RecordingModel, recording: MeetingRecording
    ):
        """Update an existing recording."""
        existing.display_name = recording.display_name
        existing.duration = recording.duration
        existing.video_file_size = recording.video_file_size
        existing.is_mapped = recording.is_mapped if recording.is_mapped is not None else existing.is_mapped

        new_status = _normalize_enum(recording.status, ProcessingStatus)

        if existing.status not in (new_status, ProcessingStatus.UPLOADED):
            existing.status = new_status
        existing.expire_at = recording.expire_at

        existing.local_video_path = recording.local_video_path
        existing.processed_video_path = recording.processed_video_path
        existing.processed_audio_path = recording.processed_audio_path
        existing.transcription_dir = recording.transcription_dir
        existing.transcription_info = recording.transcription_info
        existing.topic_timestamps = recording.topic_timestamps
        existing.main_topics = recording.main_topics
        existing.processing_preferences = recording.processing_preferences
        existing.downloaded_at = recording.downloaded_at

        existing.failed = recording.failed
        existing.failed_at = recording.failed_at
        existing.failed_reason = recording.failed_reason
        existing.failed_at_stage = recording.failed_at_stage
        existing.retry_count = recording.retry_count

        meta = _build_source_metadata_payload(recording)
        if existing.source is None:
            source = SourceMetadataModel(
                recording_id=existing.id,
                source_type=_normalize_enum(recording.source_type, SourceType),
                source_key=recording.source_key,
                meta=meta,
            )
            session.add(source)
        else:
            existing.source.source_type = _normalize_enum(recording.source_type, SourceType)
            existing.source.source_key = recording.source_key
            existing_meta = existing.source.meta or {}
            merged_meta = dict(existing_meta)
            merged_meta.update(meta)
            existing.source.meta = merged_meta

        existing_outputs: dict[TargetType, OutputTargetModel] = {}
        for out in existing.outputs:
            key = _normalize_enum(out.target_type, TargetType)
            existing_outputs[key] = out

        for target in recording.output_targets:
            target_type_value = _normalize_enum(target.target_type, TargetType)
            db_target = existing_outputs.get(target_type_value)
            target_status = _normalize_enum(target.status, TargetStatus)
            if db_target:
                db_target.status = target_status  # type: ignore[assignment]
                db_target.target_meta = target.target_meta
                db_target.uploaded_at = target.uploaded_at
            else:
                session.add(
                    OutputTargetModel(
                        recording_id=existing.id,
                        target_type=target_type_value,
                        status=target_status,
                        target_meta=target.target_meta,
                        uploaded_at=target.uploaded_at,
                    )
                )

        existing_stages: dict[ProcessingStageType, ProcessingStageModel] = {}
        for stage in existing.processing_stages:
            key = _normalize_enum(stage.stage_type, ProcessingStageType)
            existing_stages[key] = stage

        for stage in recording.processing_stages:
            stage_type_value = _normalize_enum(stage.stage_type, ProcessingStageType)
            stage_status = _normalize_enum(stage.status, ProcessingStageStatus)
            db_stage = existing_stages.get(stage_type_value)
            if db_stage:
                db_stage.status = stage_status
                db_stage.failed = stage.failed
                db_stage.failed_at = stage.failed_at
                db_stage.failed_reason = stage.failed_reason
                db_stage.retry_count = stage.retry_count
                db_stage.stage_meta = stage.stage_meta
                db_stage.completed_at = stage.completed_at
            else:
                session.add(
                    ProcessingStageModel(
                        recording_id=existing.id,
                        stage_type=stage_type_value,
                        status=stage_status,
                        failed=stage.failed,
                        failed_at=stage.failed_at,
                        failed_reason=stage.failed_reason,
                        retry_count=stage.retry_count,
                        stage_meta=stage.stage_meta,
                        completed_at=stage.completed_at,
                    )
                )

        existing.updated_at = datetime.now()
        session.add(existing)

    async def _create_new_recording(self, session: AsyncSession, recording: MeetingRecording):
        """Create a new recording."""
        db_recording = RecordingModel(
            display_name=recording.display_name,
            start_time=_parse_start_time(recording.start_time),
            duration=recording.duration,
            status=recording.status,
            is_mapped=recording.is_mapped,
            expire_at=recording.expire_at,
            local_video_path=recording.local_video_path,
            processed_video_path=recording.processed_video_path,
            processed_audio_path=recording.processed_audio_path,
            transcription_dir=recording.transcription_dir,
            video_file_size=recording.video_file_size,
            transcription_info=recording.transcription_info,
            topic_timestamps=recording.topic_timestamps,
            main_topics=recording.main_topics,
            processing_preferences=recording.processing_preferences,
            downloaded_at=recording.downloaded_at,
            failed=recording.failed,
            failed_at=recording.failed_at,
            failed_reason=recording.failed_reason,
            failed_at_stage=recording.failed_at_stage,
            retry_count=recording.retry_count,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        session.add(db_recording)
        await session.flush()
        recording.db_id = db_recording.id

        meta = _build_source_metadata_payload(recording)
        source_model = SourceMetadataModel(
            recording_id=db_recording.id,
            source_type=_normalize_enum(recording.source_type, SourceType),
            source_key=recording.source_key,
            meta=meta,
        )
        session.add(source_model)
        await session.flush()

        for target in recording.output_targets:
            session.add(
                OutputTargetModel(
                    recording_id=db_recording.id,
                    target_type=_normalize_enum(target.target_type, TargetType),
                    status=_normalize_enum(target.status, TargetStatus),
                    target_meta=target.target_meta,
                    uploaded_at=target.uploaded_at,
                )
            )

        # Save processing stages
        for stage in recording.processing_stages:
            session.add(
                ProcessingStageModel(
                    recording_id=db_recording.id,
                    stage_type=_normalize_enum(stage.stage_type, ProcessingStageType),
                    status=_normalize_enum(stage.status, ProcessingStageStatus),
                    failed=stage.failed,
                    failed_at=stage.failed_at,
                    failed_reason=stage.failed_reason,
                    retry_count=stage.retry_count,
                    stage_meta=stage.stage_meta,
                    completed_at=stage.completed_at,
                )
            )

    async def get_recordings(self, status: ProcessingStatus | None = None) -> list[MeetingRecording]:
        """Get recordings from the database."""
        async with self.async_session() as session:
            try:
                query = select(RecordingModel).options(
                    selectinload(RecordingModel.source),
                    selectinload(RecordingModel.outputs),
                    selectinload(RecordingModel.processing_stages),
                )
                if status:
                    query = query.where(RecordingModel.status == status)
                query = query.order_by(RecordingModel.start_time.desc())

                result = await session.execute(query)
                db_recordings = result.scalars().all()

                recordings = [self._convert_db_to_model(db_recording) for db_recording in db_recordings]

                logger.debug(
                    f"Got recordings from the database: count={len(recordings)} | status={status.value if status else 'all'}"
                )
                return recordings

            except Exception as e:
                logger.error(f"Error getting recordings: status={status.value if status else 'all'} | error={e}")
                return []

    async def update_recording(self, recording: MeetingRecording):
        """Update a recording in the database."""
        async with self.async_session() as session:
            try:
                db_recording = await session.get(
                    RecordingModel,
                    recording.db_id,
                    options=[
                        selectinload(RecordingModel.source),
                        selectinload(RecordingModel.outputs),
                        selectinload(RecordingModel.processing_stages),
                    ],
                )
                if not db_recording:
                    logger.error(f"Recording not found: recording_id={recording.db_id}")
                    return

                await self._update_existing_recording(session, db_recording, recording)

                await session.commit()

                logger.debug(f"Recording updated: recording={recording.display_name} | recording_id={recording.db_id}")

            except Exception as e:
                await session.rollback()
                logger.error(
                    f"Error updating recording: recording={recording.display_name} | recording_id={recording.db_id} | error={e}"
                )
                raise

    def _convert_db_to_model(self, db_recording: RecordingModel) -> MeetingRecording:
        """Convert a recording from the database to a model."""
        if isinstance(db_recording.start_time, datetime):
            dt = db_recording.start_time
            if dt.tzinfo is not None:
                dt_utc = dt.astimezone(ZoneInfo("UTC"))
            else:
                dt_utc = dt.replace(tzinfo=ZoneInfo("UTC"))

            start_time_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            start_time_str = str(db_recording.start_time)

        source_type_raw = db_recording.source.source_type if db_recording.source else SourceType.ZOOM
        source_type = _normalize_enum(source_type_raw, SourceType)
        source_key = db_recording.source.source_key if db_recording.source else ""
        source_meta = (db_recording.source.meta if db_recording.source and db_recording.source.meta else {}) or {}

        outputs = [
            OutputTarget(
                target_type=_normalize_enum(out.target_type, TargetType),
                status=_normalize_enum(out.status, TargetStatus),
                target_meta=out.target_meta,
                uploaded_at=out.uploaded_at,
            )
            for out in db_recording.outputs
        ]

        processing_stages = [
            ProcessingStage(
                stage_type=_normalize_enum(stage.stage_type, ProcessingStageType),
                status=_normalize_enum(stage.status, ProcessingStageStatus),
                failed=stage.failed,
                failed_at=stage.failed_at,
                failed_reason=stage.failed_reason,
                retry_count=stage.retry_count,
                stage_meta=stage.stage_meta,
                completed_at=stage.completed_at,
            )
            for stage in db_recording.processing_stages
        ]

        meeting_data = {
            "user_id": db_recording.user_id,
            "display_name": db_recording.display_name,
            "start_time": start_time_str,
            "duration": db_recording.duration,
            "status": db_recording.status,
            "is_mapped": db_recording.is_mapped,
            "expire_at": db_recording.expire_at,
            "source_type": source_type,
            "source_key": source_key,
            "source_metadata": source_meta,
            "local_video_path": db_recording.local_video_path,
            "processed_video_path": db_recording.processed_video_path,
            "processed_audio_path": db_recording.processed_audio_path,
            "transcription_dir": db_recording.transcription_dir,
            "video_file_size": db_recording.video_file_size,
            "transcription_info": db_recording.transcription_info,
            "topic_timestamps": db_recording.topic_timestamps,
            "main_topics": db_recording.main_topics,
            "processing_preferences": db_recording.processing_preferences,
            "downloaded_at": db_recording.downloaded_at,
            "output_targets": outputs,
            "processing_stages": processing_stages,
            "failed": db_recording.failed,
            "failed_at": db_recording.failed_at,
            "failed_reason": db_recording.failed_reason,
            "failed_at_stage": db_recording.failed_at_stage,
            "retry_count": db_recording.retry_count,
        }

        if source_meta:
            meeting_data.update(
                {
                    "id": source_meta.get("meeting_id", ""),
                    "account": source_meta.get("account", "default"),
                    "video_file_download_url": source_meta.get("video_file_download_url"),
                    "download_access_token": source_meta.get("download_access_token"),
                    "password": source_meta.get("password"),
                    "recording_play_passcode": source_meta.get("recording_play_passcode"),
                    "part_index": source_meta.get("part_index"),
                    "total_visible_parts": source_meta.get("total_visible_parts"),
                }
            )

        recording = MeetingRecording(meeting_data)
        recording.db_id = db_recording.id
        return recording

    async def close(self):
        """Close database connection."""
        if hasattr(self, "engine") and self.engine is not None:
            await self.engine.dispose()
            logger.info("Database connection closed")
