"""Async recording repository with multi-tenancy"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload

from api.helpers.blank_record import (
    BLANK_REASON_TOO_SHORT,
    apply_blank_record,
    is_mts_link_blank,
    positive_duration_seconds,
    preserve_mts_recording_duration,
)
from api.helpers.text import collapse_whitespace
from api.schemas.recording.filters import OperationalState
from database.models import OutputTargetModel, RecordingModel, SourceMetadataModel
from database.playlist_models import PlaylistItemModel, PlaylistModel
from logger import format_details, format_status_change, get_logger
from models.recording import ProcessingStatus, SourceType, TargetStatus

logger = get_logger()

RECORDING_SORT_FIELDS = frozenset({"created_at", "updated_at", "start_time", "display_name", "status", "view_count"})
_RECORDING_SORT_COLUMNS = {"view_count": "share_view_count"}
DEFAULT_RECORDING_SORT = "start_time"
UNTITLED_DISPLAY_NAME = "Untitled"


def _normalized_display_name(display_name: str) -> str:
    collapsed = collapse_whitespace(display_name)
    return collapsed or UNTITLED_DISPLAY_NAME


def _recording_order_clause(sort_by: str, sort_order: str):
    """Primary sort plus a stable id tie-break. Nulls always sort last."""
    field = sort_by if sort_by in RECORDING_SORT_FIELDS else DEFAULT_RECORDING_SORT
    column = getattr(RecordingModel, _RECORDING_SORT_COLUMNS.get(field, field))
    descending = sort_order == "desc"
    primary = column.desc().nulls_last() if descending else column.asc().nulls_last()
    tie = RecordingModel.id.desc() if descending else RecordingModel.id.asc()
    return primary, tie


def operational_state_conditions():
    """Exclusive operational categories shared by Home and catalog filters."""
    r = RecordingModel
    healthy = r.failed.is_(False)
    running = and_(healthy, r.on_pause.is_(False))
    waiting = r.status.in_([ProcessingStatus.PENDING_SOURCE, ProcessingStatus.PENDING_CONVERSION])
    return {
        "error": r.failed.is_(True),
        "paused": and_(healthy, r.on_pause.is_(True)),
        "waiting_source": and_(running, waiting),
        "in_progress": and_(running, ~waiting, r.on_air.is_(True)),
    }


def merge_mts_link_source_metadata(existing_meta: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    """Merge MTS discovery metadata without wiping a prepare-time MP4 URL.

    Sync often has no converted-record URL even after prepare stored ``download_url``.
    """
    merged = dict(existing_meta)
    payload = dict(incoming or {})
    existing_url = existing_meta.get("download_url")
    if existing_url and not payload.get("download_url"):
        payload["download_url"] = existing_url
        payload["needs_mp4"] = False
        payload["source_processing_incomplete"] = False
    merged.update(payload)
    return merged


class RecordingRepository:
    """Repository for working with recordings."""

    def __init__(self, session: AsyncSession):
        """
        Initialize repository.

        Args:
            session: Async database session
        """
        self.session = session

    async def get_by_id(self, recording_id: int, user_id: str, include_deleted: bool = False) -> RecordingModel | None:
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
                selectinload(RecordingModel.template),
                selectinload(RecordingModel.owner),
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
                selectinload(RecordingModel.template),
                selectinload(RecordingModel.owner),
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
                selectinload(RecordingModel.template),
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

    # ========================================================================
    # Unified filtered queries (SQL-level filtering)
    # ========================================================================

    def _apply_filters(
        self,
        query,
        user_id: str,
        *,
        template_ids: list[int] | None = None,
        source_ids: list[int] | None = None,
        statuses: list[str] | None = None,
        failed: bool | None = None,
        operational_state: OperationalState | None = None,
        is_mapped: bool | None = None,
        exclude_blank: bool = True,
        include_deleted: bool = False,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        search: str | None = None,
    ):
        """Apply common recording filters to a SQLAlchemy query."""
        query = query.where(RecordingModel.user_id == user_id)

        if not include_deleted:
            query = query.where(RecordingModel.deleted == False)  # noqa: E712

        if template_ids:
            query = query.where(RecordingModel.template_id.in_(template_ids))

        if source_ids:
            query = query.where(RecordingModel.input_source_id.in_(source_ids))

        if statuses:
            has_failed = "FAILED" in statuses
            other_statuses = [s for s in statuses if s != "FAILED"]

            if has_failed and other_statuses:
                query = query.where(
                    or_(
                        RecordingModel.status.in_(other_statuses),
                        RecordingModel.failed == True,  # noqa: E712
                    )
                )
            elif has_failed:
                query = query.where(RecordingModel.failed == True)  # noqa: E712
            else:
                query = query.where(RecordingModel.status.in_(other_statuses))

        if operational_state is not None:
            query = query.where(operational_state_conditions()[operational_state])

        if failed is not None:
            query = query.where(RecordingModel.failed == failed)

        if is_mapped is not None:
            query = query.where(RecordingModel.is_mapped == is_mapped)

        if exclude_blank:
            query = query.where(~RecordingModel.blank_record)

        if from_dt is not None:
            query = query.where(RecordingModel.start_time >= from_dt)

        if to_dt is not None:
            query = query.where(RecordingModel.start_time <= to_dt)

        if search:
            query = query.where(RecordingModel.display_name.ilike(f"%{search}%"))

        return query

    async def home_summary(self, user_id: str) -> dict[str, int]:
        """One bounded aggregate query; no relationships or media storage access."""
        public_playlist_recordings = (
            select(PlaylistItemModel.recording_id)
            .join(PlaylistModel, PlaylistModel.id == PlaylistItemModel.playlist_id)
            .where(
                PlaylistModel.user_id == user_id,
                PlaylistModel.share_enabled.is_(True),
                PlaylistModel.share_token.is_not(None),
            )
        )
        query = select(
            func.count(RecordingModel.id).label("total"),
            func.count(RecordingModel.id)
            .filter(
                or_(
                    and_(RecordingModel.share_enabled.is_(True), RecordingModel.share_token.is_not(None)),
                    and_(
                        RecordingModel.id.in_(public_playlist_recordings),
                        RecordingModel.processed_video_path.is_not(None),
                        RecordingModel.processed_video_path != "",
                    ),
                ),
                RecordingModel.delete_state == "active",
            )
            .label("published"),
            *(
                func.count(RecordingModel.id).filter(condition).label(name)
                for name, condition in operational_state_conditions().items()
            ),
        )
        query = self._apply_filters(query, user_id)
        result = await self.session.execute(query)
        return dict(result.mappings().one())

    async def list_filtered(
        self,
        user_id: str,
        *,
        template_ids: list[int] | None = None,
        source_ids: list[int] | None = None,
        statuses: list[str] | None = None,
        failed: bool | None = None,
        operational_state: OperationalState | None = None,
        is_mapped: bool | None = None,
        exclude_blank: bool = True,
        include_deleted: bool = False,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        search: str | None = None,
        sort_by: str = DEFAULT_RECORDING_SORT,
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
        include_processing_stages: bool = True,
    ) -> tuple[list[RecordingModel], int]:
        """
        Get paginated, filtered recordings with total count.

        All filters are applied at the SQL level for correct results regardless
        of total record count.
        """
        # Total count
        count_query = select(func.count(RecordingModel.id))
        count_query = self._apply_filters(
            count_query,
            user_id,
            template_ids=template_ids,
            source_ids=source_ids,
            statuses=statuses,
            failed=failed,
            operational_state=operational_state,
            is_mapped=is_mapped,
            exclude_blank=exclude_blank,
            include_deleted=include_deleted,
            from_dt=from_dt,
            to_dt=to_dt,
            search=search,
        )
        total = (await self.session.execute(count_query)).scalar() or 0

        # Data query with eager loading
        stage_load = (
            selectinload(RecordingModel.processing_stages)
            if include_processing_stages
            else raiseload(RecordingModel.processing_stages)
        )
        data_query = select(RecordingModel).options(
            selectinload(RecordingModel.source).selectinload(SourceMetadataModel.input_source),
            selectinload(RecordingModel.outputs).selectinload(OutputTargetModel.preset),
            stage_load,
            selectinload(RecordingModel.input_source),
            selectinload(RecordingModel.template),
            selectinload(RecordingModel.owner),
        )
        data_query = self._apply_filters(
            data_query,
            user_id,
            template_ids=template_ids,
            source_ids=source_ids,
            statuses=statuses,
            failed=failed,
            operational_state=operational_state,
            is_mapped=is_mapped,
            exclude_blank=exclude_blank,
            include_deleted=include_deleted,
            from_dt=from_dt,
            to_dt=to_dt,
            search=search,
        )

        data_query = data_query.order_by(*_recording_order_clause(sort_by, sort_order))

        # Pagination
        offset = (page - 1) * per_page
        data_query = data_query.offset(offset).limit(per_page)

        result = await self.session.execute(data_query)
        recordings = list(result.scalars().all())

        return recordings, total

    async def get_filtered_ids(
        self,
        user_id: str,
        *,
        template_ids: list[int] | None = None,
        source_ids: list[int] | None = None,
        statuses: list[str] | None = None,
        failed: bool | None = None,
        operational_state: OperationalState | None = None,
        is_mapped: bool | None = None,
        exclude_blank: bool = True,
        include_deleted: bool = False,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        search: str | None = None,
        sort_by: str = DEFAULT_RECORDING_SORT,
        sort_order: str = "desc",
        limit: int = 50,
    ) -> list[int]:
        """Get filtered recording IDs for bulk operations."""
        query = select(RecordingModel.id)
        query = self._apply_filters(
            query,
            user_id,
            template_ids=template_ids,
            source_ids=source_ids,
            statuses=statuses,
            failed=failed,
            operational_state=operational_state,
            is_mapped=is_mapped,
            exclude_blank=exclude_blank,
            include_deleted=include_deleted,
            from_dt=from_dt,
            to_dt=to_dt,
            search=search,
        )

        query = query.order_by(*_recording_order_clause(sort_by, sort_order))

        query = query.limit(limit)

        result = await self.session.execute(query)
        return [row[0] for row in result.all()]

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
        display_name = _normalized_display_name(display_name)

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
            template_id=kwargs.get("template_id"),
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
        await self.sync_retention_deadline(recording, user_config)

        logger.info(f"Created recording | {format_details(id=recording.id, source=input_source_id)}")

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

        if isinstance(recording.display_name, str):
            recording.display_name = _normalized_display_name(recording.display_name)

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

        logger.info(f"Created output target | {format_details(rec=recording.id, target=target_type)}")
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

        logger.debug(f"Marked output UPLOADING | {format_details(target=output_target.id, rec=recording.id)}")

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

        logger.warning(
            f"Marked output FAILED | {format_details(target=output_target.id, rec=recording.id, error=error_message[:100])}"
        )

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

            logger.info(f"Upload result saved | {format_details(rec=recording.id, target=target_type)}")
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

            logger.info(f"Upload result created | {format_details(rec=recording.id, target=target_type)}")

        # Refresh recording to ensure outputs are loaded
        await self.session.refresh(recording, ["outputs"])

        # Update aggregate recording status (UPLOADING → READY or PROCESSED → READY)
        update_aggregate_status(recording)
        logger.info(f"Aggregate status updated | {format_details(rec=recording.id, status=recording.status)}")

        return output

    async def find_by_source_key(
        self,
        user_id: str,
        source_type: SourceType,
        source_key: str,
        start_time: datetime | None = None,
        *,
        require_start_time_in_lookup: bool = True,
    ) -> RecordingModel | None:
        """
        Find a recording by ``source_key`` (and user).

        ``require_start_time_in_lookup`` controls whether ``start_time`` is part of the SQL match:

        - **True (default)** — used for sources whose identity is the pair
          ``(source_key, start_time)`` (e.g. Zoom: one logical meeting instance per start).
        - **False** — match **only** ``user_id`` + ``source_type`` + ``source_key``.
          Used for Yandex Disk after we switched to content-stable keys (``md5`` / ``resource_id``):
          ``start_time`` is derived from file ``modified`` and must not split one file into
          multiple rows when the remote mtime or path metadata changes.
        """
        if require_start_time_in_lookup and start_time is None:
            raise ValueError("start_time is required when require_start_time_in_lookup=True")

        filters = [
            RecordingModel.user_id == user_id,
            SourceMetadataModel.source_type == source_type,
            SourceMetadataModel.source_key == source_key,
        ]
        if require_start_time_in_lookup:
            filters.append(RecordingModel.start_time == start_time)

        query = (
            select(RecordingModel)
            .options(
                selectinload(RecordingModel.source).selectinload(SourceMetadataModel.input_source),
                selectinload(RecordingModel.outputs).selectinload(OutputTargetModel.preset),
                selectinload(RecordingModel.processing_stages),
                selectinload(RecordingModel.input_source),
                selectinload(RecordingModel.template),
            )
            .join(SourceMetadataModel)
            .where(*filters)
            .order_by(RecordingModel.id.asc())
            .limit(1)
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
            source_key: Canonical source key to store on ``SourceMetadata`` after upsert
            source_metadata: Source metadata
            user_config: User configuration for retention settings

        Keyword-only (via ``**kwargs``, consumed here, not passed to the ORM model):

            require_start_time_in_lookup:
                If True (default), an existing row is found only when ``start_time`` matches
                as well as ``source_key``. If False, lookup uses ``source_key`` only — needed
                for Yandex Disk stable keys; see :meth:`find_by_source_key`.
            alternate_source_keys:
                Extra keys to try when ``require_start_time_in_lookup`` is False (e.g. legacy
                path-based key before migrating the row to a hash-based key).
            uploaded_allow_metadata_refresh:
                If True and status is ``UPLOADED``, still merge ``source_metadata`` and migrate
                ``source_key`` when the remote file was renamed (Yandex sync).

            Other ``kwargs`` are forwarded to the new ``RecordingModel`` / status logic
            (``template_id``, ``is_mapped``, ``blank_record``, etc.).

        Returns:
            Tuple (recording, was_created)
        """
        alternate_source_keys: list[str] | None = kwargs.pop("alternate_source_keys", None)
        require_start_time_in_lookup: bool = kwargs.pop("require_start_time_in_lookup", True)
        uploaded_allow_metadata_refresh: bool = kwargs.pop("uploaded_allow_metadata_refresh", False)

        if require_start_time_in_lookup:
            existing = await self.find_by_source_key(
                user_id, source_type, source_key, start_time, require_start_time_in_lookup=True
            )
        else:
            keys = list(dict.fromkeys([source_key, *list(alternate_source_keys or [])]))
            keys = [k for k in keys if k]
            existing = None
            for k in keys:
                candidate = await self.find_by_source_key(
                    user_id, source_type, k, start_time, require_start_time_in_lookup=False
                )
                if candidate:
                    existing = candidate
                    break

        if existing is None and not require_start_time_in_lookup:
            try:
                async with self.session.begin_nested():
                    return await self._insert_recording(
                        user_id=user_id,
                        input_source_id=input_source_id,
                        display_name=display_name,
                        start_time=start_time,
                        duration=duration,
                        source_type=source_type,
                        source_key=source_key,
                        source_metadata=source_metadata,
                        user_config=user_config,
                        kwargs=kwargs,
                    )
            except IntegrityError:
                existing = await self.find_by_source_key(
                    user_id, source_type, source_key, start_time, require_start_time_in_lookup=False
                )
                if existing is None:
                    raise

        if existing:
            # Don't update deleted recordings (user deleted manually)
            if existing.deleted:
                logger.info(f"Skipped: recording deleted | {format_details(rec=existing.id)}")
                return existing, False

            # Update existing recording, but only if status is not UPLOADED
            if existing.status != ProcessingStatus.UPLOADED:
                if not require_start_time_in_lookup and source_type != SourceType.EXTERNAL_URL:
                    existing.start_time = start_time
                previous_meta = (
                    existing.source.meta if existing.source and isinstance(existing.source.meta, dict) else {}
                )
                previous_title = previous_meta.get("title")
                refresh_title = (
                    source_type != SourceType.EXTERNAL_URL
                    or not isinstance(previous_title, str)
                    or existing.display_name == _normalized_display_name(previous_title)
                )
                if refresh_title:
                    existing.display_name = _normalized_display_name(display_name)
                if duration > 0 or source_type not in (SourceType.MTS_LINK, SourceType.EXTERNAL_URL):
                    if source_type == SourceType.MTS_LINK and preserve_mts_recording_duration(
                        has_downloaded_media=bool(existing.local_video_path),
                        existing_duration=existing.duration,
                    ):
                        pass
                    else:
                        existing.duration = duration
                existing.video_file_size = kwargs.get("video_file_size", existing.video_file_size)

                source_processing_incomplete = kwargs.get("source_processing_incomplete", False)
                if source_type == SourceType.MTS_LINK and existing.source:
                    existing_meta = existing.source.meta if isinstance(existing.source.meta, dict) else {}
                    source_metadata = merge_mts_link_source_metadata(existing_meta, source_metadata)
                    source_processing_incomplete = bool(source_metadata.get("source_processing_incomplete"))

                if "is_mapped" in kwargs and (source_type != SourceType.EXTERNAL_URL or kwargs["is_mapped"]):
                    old_is_mapped = existing.is_mapped
                    existing.is_mapped = kwargs["is_mapped"]

                    if existing.status not in (
                        ProcessingStatus.PENDING_SOURCE,
                        ProcessingStatus.PENDING_CONVERSION,
                    ) and existing.status in [
                        ProcessingStatus.INITIALIZED,
                        ProcessingStatus.SKIPPED,
                    ]:
                        if old_is_mapped != existing.is_mapped:
                            existing.status = (
                                ProcessingStatus.INITIALIZED if existing.is_mapped else ProcessingStatus.SKIPPED
                            )

                if existing.status == ProcessingStatus.PENDING_SOURCE and not source_processing_incomplete:
                    meta = existing.source.meta if existing.source and isinstance(existing.source.meta, dict) else {}
                    if not meta.get("conversion_id"):
                        is_blank = kwargs.get("blank_record", False)
                        if is_blank:
                            existing.status = ProcessingStatus.SKIPPED
                        elif existing.is_mapped:
                            existing.status = ProcessingStatus.INITIALIZED
                        else:
                            existing.status = ProcessingStatus.SKIPPED
                        logger.info(
                            f"{format_status_change('Recording', 'PENDING_SOURCE', existing.status)} | {format_details(rec=existing.id)}"
                        )

                if "template_id" in kwargs and (source_type != SourceType.EXTERNAL_URL or kwargs["template_id"]):
                    existing.template_id = kwargs["template_id"]

                is_blank = bool(kwargs.get("blank_record", False))
                if source_type == SourceType.MTS_LINK:
                    is_blank = is_blank or is_mts_link_blank(positive_duration_seconds(existing.duration))
                if is_blank:
                    apply_blank_record(existing, True, reason=BLANK_REASON_TOO_SHORT)

                if existing.source:
                    if existing.source.source_key != source_key:
                        existing.source.source_key = source_key
                    existing_meta = existing.source.meta if isinstance(existing.source.meta, dict) else {}
                    if source_type == SourceType.MTS_LINK:
                        existing.source.meta = source_metadata or existing_meta
                    else:
                        merged_meta = dict(existing_meta)
                        merged_meta.update(source_metadata or {})
                        existing.source.meta = merged_meta

                existing.updated_at = datetime.now(UTC)

                logger.info(f"Updated recording | {format_details(rec=existing.id, status=existing.status)}")

                await self.session.flush()
                return existing, False
            # Recording already uploaded — optionally refresh source metadata / canonical key (e.g. Yandex rename)
            if uploaded_allow_metadata_refresh and existing.source:
                if not require_start_time_in_lookup and source_type != SourceType.EXTERNAL_URL:
                    existing.start_time = start_time
                if existing.source.source_key != source_key:
                    existing.source.source_key = source_key
                existing_meta = existing.source.meta if isinstance(existing.source.meta, dict) else {}
                merged_meta = dict(existing_meta)
                merged_meta.update(source_metadata or {})
                existing.source.meta = merged_meta
                existing.updated_at = datetime.now(UTC)
                await self.session.flush()
                logger.info(f"Refreshed source metadata (uploaded) | {format_details(rec=existing.id, key=source_key)}")
                return existing, False
            logger.info(f"Skipped: already uploaded | {format_details(rec=existing.id)}")
            return existing, False
        return await self._insert_recording(
            user_id=user_id,
            input_source_id=input_source_id,
            display_name=display_name,
            start_time=start_time,
            duration=duration,
            source_type=source_type,
            source_key=source_key,
            source_metadata=source_metadata,
            user_config=user_config,
            kwargs=kwargs,
        )

    async def _insert_recording(
        self,
        *,
        user_id: str,
        input_source_id: int | None,
        display_name: str,
        start_time: datetime,
        duration: int,
        source_type: SourceType,
        source_key: str,
        source_metadata: dict[str, Any] | None,
        user_config: dict | None,
        kwargs: dict[str, Any],
    ) -> tuple[RecordingModel, bool]:
        display_name = _normalized_display_name(display_name)
        is_mapped = kwargs.get("is_mapped", False)
        is_blank = kwargs.get("blank_record", False)
        source_processing_incomplete = kwargs.get("source_processing_incomplete", False)

        if source_processing_incomplete:
            status = ProcessingStatus.PENDING_SOURCE
        elif is_blank:
            status = ProcessingStatus.SKIPPED
        elif is_mapped:
            status = ProcessingStatus.INITIALIZED
        else:
            status = ProcessingStatus.SKIPPED

        retention = user_config.get("retention", {}) if isinstance(user_config, dict) else {}
        auto_expire_days = retention.get("auto_expire_days", 90)

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
        await self.sync_retention_deadline(recording, user_config)

        logger.info(f"Created recording | {format_details(rec=recording.id, mapped=is_mapped, status=status)}")

        return recording, True

    async def sync_retention_deadline(self, recording: RecordingModel, user_config: dict | None) -> None:
        """Apply the effective flag. Does not write an override."""
        from api.services.retention import apply_retention_deadline, template_retention_flags

        flags = await template_retention_flags(self.session, [recording])
        apply_retention_deadline(recording, flags.get(recording.id, False), user_config or {})
        await self.session.flush()

    async def assign_retention_exempt(
        self, recording: RecordingModel, override: bool | None, user_config: dict
    ) -> None:
        """Store the recording override. None follows the template again."""
        recording.retention_exempt = override
        recording.updated_at = datetime.now(UTC)
        await self.sync_retention_deadline(recording, user_config)

    async def sync_inherited_retention(self, user_id: str, user_config: dict) -> None:
        """Refresh auto-hide dates for this user's recordings that follow a template."""
        from sqlalchemy import select

        from api.services.retention import apply_retention_deadline, template_retention_flags

        recordings = list(
            (
                await self.session.execute(
                    select(RecordingModel).where(
                        RecordingModel.user_id == user_id,
                        RecordingModel.retention_exempt.is_(None),
                        RecordingModel.deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        flags = await template_retention_flags(self.session, recordings)
        for recording in recordings:
            apply_retention_deadline(recording, flags.get(recording.id, False), user_config)
        await self.session.flush()

    def _hide(self, recording: RecordingModel, user_config: dict, reason: str) -> None:
        from api.services.retention import hard_delete_deadline, revoke_pipeline

        now = datetime.now(UTC)
        revoke_pipeline(recording)
        recording.deleted = True
        recording.delete_state = "soft"
        recording.deletion_reason = reason
        recording.deleted_at = now
        recording.expire_at = None
        recording.updated_at = now
        hard_days = int((user_config.get("retention") or {}).get("hard_delete_days") or 30)
        recording.soft_deleted_at = now
        recording.hard_delete_at = hard_delete_deadline(now, hard_days)

    async def soft_delete(self, recording: RecordingModel, user_config: dict) -> None:
        """Hide a recording the user deleted. Files stay until hard_delete_at."""
        self._hide(recording, user_config, "manual")
        await self.session.flush()
        logger.info(f"Soft deleted recording | {format_details(rec=recording.id)}")

    async def auto_expire(self, recording: RecordingModel, user_config: dict, *, template_exempt: bool = False) -> None:
        """Hide a recording whose auto-hide date passed. An effective exemption skips it."""
        from api.services.retention import effective_retention_exempt

        if effective_retention_exempt(recording.retention_exempt, template_exempt) or recording.deleted:
            return
        self._hide(recording, user_config, "expired")
        await self.session.flush()
        logger.info(f"Auto-expired recording | {format_details(rec=recording.id)}")

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

        from api.services.retention import apply_retention_deadline, template_retention_flags

        flags = await template_retention_flags(self.session, [recording])
        recording.expire_at = None
        apply_retention_deadline(recording, flags.get(recording.id, False), user_config)

        recording.updated_at = datetime.now(UTC)

        await self.session.flush()

        logger.info(f"Restored recording | {format_details(rec=recording.id)}")

    async def wipe_recording_storage(
        self, recording: RecordingModel
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Delete every object under the recording prefix, plus any path stored outside it."""
        from file_storage.factory import get_storage_backend
        from file_storage.path_builder import StoragePathBuilder, to_storage_key

        storage = get_storage_backend()
        deleted: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        prefixes: list[str] = []

        owner = recording.owner
        if owner is None and recording.user_id:
            from database.auth_models import UserModel

            owner = await self.session.get(UserModel, recording.user_id)
        if owner is not None and owner.user_slug is not None:
            root = to_storage_key(StoragePathBuilder().recording_root(owner.user_slug, recording.id))
            prefixes.append(root.rstrip("/") + "/")
        if recording.transcription_dir:
            tx_prefix = to_storage_key(recording.transcription_dir).rstrip("/") + "/"
            if tx_prefix not in prefixes:
                prefixes.append(tx_prefix)

        seen: set[str] = set()
        for prefix in prefixes:
            try:
                keys = await storage.list_keys(prefix)
            except Exception as exc:
                errors.append({"type": "prefix", "path": prefix, "error": str(exc)})
                logger.warning(f"Failed to list recording prefix | prefix={prefix} | error={exc}")
                continue
            for key in keys:
                if key in seen:
                    continue
                seen.add(key)
                try:
                    if await storage.delete(key):
                        deleted.append({"type": "object", "path": key, "is_dir": False})
                except Exception as exc:
                    errors.append({"type": "object", "path": key, "error": str(exc)})
                    logger.warning(f"Failed to delete object | key={key} | error={exc}")

        for label, key in (
            ("local_video", recording.local_video_path),
            ("processed_video", recording.processed_video_path),
            ("processed_audio", recording.processed_audio_path),
        ):
            if not key or key in seen:
                continue
            try:
                if await storage.exists(key) and await storage.delete(key):
                    deleted.append({"type": label, "path": key, "is_dir": False})
            except Exception as exc:
                errors.append({"type": label, "path": key, "error": str(exc)})

        error_paths = {str(item["path"]) for item in errors if item.get("path")}
        # A failed prefix listing must keep transcription_dir so the next wipe can retry it.
        # A stray key that failed to delete stays on the row; False from delete means it is already gone.
        if not any(item.get("type") == "prefix" for item in errors):
            recording.transcription_dir = None
        for attr in ("local_video_path", "processed_video_path", "processed_audio_path"):
            current = getattr(recording, attr)
            if current and current in error_paths:
                continue
            setattr(recording, attr, None)
        return deleted, errors

    async def delete(self, recording: RecordingModel) -> None:
        """Remove the recording prefix and the database row. Account deletion uses this too."""
        _deleted, errors = await self.wipe_recording_storage(recording)
        if errors:
            raise RuntimeError(f"Recording {recording.id} storage wipe failed: {errors[0].get('error')}")
        await self.session.delete(recording)
        await self.session.flush()
        logger.info(f"Hard deleted recording | {format_details(rec=recording.id)}")


async def sync_user_inherited_retention(session: AsyncSession, user_id: str) -> None:
    """Apply the live template flag to every recording of this user that has no override."""
    from api.repositories.config_repos import UserConfigRepository

    user_config = await UserConfigRepository(session).get_effective_config(user_id)
    await RecordingRepository(session).sync_inherited_retention(user_id, user_config)
