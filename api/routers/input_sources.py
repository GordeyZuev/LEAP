"""Input source endpoints"""

import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.dependencies import get_db_session
from api.repositories.auth_repos import UserCredentialRepository
from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import InputSourceRepository, RecordingTemplateRepository
from api.schemas.common.pagination import paginate_list
from api.schemas.template import (
    BulkSyncRequest,
    InputSourceCreate,
    InputSourceResponse,
    InputSourceUpdate,
    SourceListResponse,
)
from api.schemas.template.sync import BulkSyncTaskResponse, SourceSyncTaskResponse
from api.zoom_api import ZoomAPI, ZoomRecordingProcessingError
from database.auth_models import UserModel
from logger import format_details, get_logger, short_task_id, short_user_id
from models.recording import SourceType
from models.zoom_auth import create_zoom_credentials

router = APIRouter(prefix="/api/v1/sources", tags=["Input Sources"])
logger = get_logger()


def _get_best_video_file(recording_files: list | None) -> dict | None:
    """Select best video file from recording files (prefer shared_screen_with_speaker_view)."""
    if not recording_files:
        return None

    for file in recording_files:
        if file.get("file_type") == "MP4" and file.get("recording_type") == "shared_screen_with_speaker_view":
            return file

    for file in recording_files:
        if file.get("file_type") == "MP4":
            return file

    return None


async def _fetch_zoom_recording_details(zoom_api, meeting_id: str) -> tuple[dict | None, str | None, bool]:
    """Fetch recording details from Zoom API. Returns (details, token, is_incomplete)."""
    try:
        meeting_details = await zoom_api.get_recording_details(meeting_id, include_download_token=True)
        download_access_token = meeting_details.get("download_access_token")
        return meeting_details, download_access_token, False
    except ZoomRecordingProcessingError:
        logger.info(f"Skipped: still being processed | {format_details(meeting=meeting_id)}")
        return None, None, True
    except Exception as e:
        logger.warning(f"Failed to get download_access_token | {format_details(meeting=meeting_id, error=str(e))}")
        return None, None, False


def _build_zoom_metadata(
    meeting: dict,
    video_file: dict | None,
    download_access_token: str | None,
    meeting_details: dict | None,
    zoom_processing_incomplete: bool,
    credentials: dict,
) -> dict:
    """Build source metadata from Zoom API response."""
    meta = {
        "meeting_id": meeting.get("uuid", meeting.get("id", "")),
        "account": credentials.get("account", ""),
        "account_id": meeting.get("account_id"),
        "host_id": meeting.get("host_id"),
        "host_email": meeting.get("host_email"),
        "share_url": meeting.get("share_url"),
        "recording_play_passcode": meeting.get("recording_play_passcode"),
        "password": meeting.get("password"),
        "timezone": meeting.get("timezone"),
        "total_size": meeting.get("total_size"),
        "recording_count": meeting.get("recording_count"),
        "download_url": video_file.get("download_url") if video_file else None,
        "play_url": video_file.get("play_url") if video_file else None,
        "download_access_token": download_access_token,
        "video_file_size": video_file.get("file_size") if video_file else None,
        "video_file_type": video_file.get("file_type") if video_file else None,
        "recording_type": video_file.get("recording_type") if video_file else None,
        "delete_time": meeting.get("delete_time"),
        "auto_delete_date": meeting.get("auto_delete_date"),
        "source_processing_incomplete": zoom_processing_incomplete,
        "zoom_api_meeting": meeting,
        "zoom_api_details": meeting_details if meeting_details else {},
    }

    # Store source user email for Master Account syncs
    if "_source_user_email" in meeting:
        meta["source_user_email"] = meeting["_source_user_email"]

    return meta


def _determine_blank_status(
    duration: float,
    video_file_size: int,
    source_processing_incomplete: bool,
    min_duration_seconds: int = 1200,
    min_file_size_mb: int = 25,
) -> bool:
    """Determine if recording should be marked as blank (skip if source is still processing).

    Args:
        duration: Recording duration in seconds.
        min_duration_seconds: Minimum duration threshold (default 1200 = 20 min).
    """
    if source_processing_incomplete:
        return False

    min_file_size_bytes = min_file_size_mb * 1024 * 1024
    return duration < min_duration_seconds or video_file_size < min_file_size_bytes


async def _sync_single_source(
    source_id: int,
    from_date: str,
    to_date: str | None,
    session: AsyncSession,
    user_id: str,
) -> dict:
    """Sync single source and save recordings to database."""
    repo = InputSourceRepository(session)
    source = await repo.find_by_id(source_id, user_id)

    if not source:
        return {
            "status": "error",
            "error": f"Source {source_id} not found",
        }

    if not source.is_active:
        return {
            "status": "error",
            "error": "Source is not active",
        }

    # Some sources don't require credentials (VIDEO_URL, public Yandex Disk links)
    credentials = {}
    _no_credential_types = {"VIDEO_URL", "LOCAL"}

    if source.source_type not in _no_credential_types:
        # Check if credential is needed (Yandex Disk public_url doesn't need one)
        source_config = source.config or {}
        needs_credential = True
        if source.source_type == "YANDEX_DISK" and source_config.get("public_url"):
            needs_credential = False

        if needs_credential:
            if not source.credential_id:
                return {
                    "status": "error",
                    "error": "Source has no credential configured",
                }

            cred_repo = UserCredentialRepository(session)
            credential = await cred_repo.get_by_id(source.credential_id)

            if not credential:
                return {
                    "status": "error",
                    "error": f"Credentials {source.credential_id} not found",
                }

            from api.auth.encryption import get_encryption

            encryption = get_encryption()
            credentials = encryption.decrypt_credentials(credential.encrypted_data)

    meetings = []
    saved_count = 0
    updated_count = 0

    if source.source_type == "ZOOM":
        try:
            # Create Zoom credentials from dict
            zoom_config = create_zoom_credentials(credentials)

            # Check if Master Account sync
            source_config = source.config or {}
            is_master = source_config.get("is_master_account", False)
            user_emails = source_config.get("user_emails") or []

            if is_master and user_emails:
                # Master Account: one token, query recordings per user email
                zoom_api = ZoomAPI(zoom_config)
                logger.info(
                    f"Master Account sync | {format_details(users=len(user_emails), source=source_id)}",
                )
                for email in user_emails:
                    try:
                        recordings_data = await zoom_api.get_recordings(
                            from_date=from_date,
                            to_date=to_date,
                            user_id=email,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to sync user | {format_details(email=email, error=str(e))}")
                        continue
                    user_meetings = recordings_data.get("meetings") or []
                    for m in user_meetings:
                        m["_source_user_email"] = email
                    meetings.extend(user_meetings)
                    logger.info(f"User recordings | {format_details(email=email, recordings=len(user_meetings))}")
            else:
                # Regular account: single sync
                zoom_api = ZoomAPI(zoom_config)
                recordings_data = await zoom_api.get_recordings(from_date=from_date, to_date=to_date)
                meetings = recordings_data.get("meetings") or []

            logger.info(f"Found recordings | {format_details(source=source_id, count=len(meetings))}")

            template_repo = RecordingTemplateRepository(session)
            templates = await template_repo.find_active_by_user(user_id)

            user_config_repo = UserConfigRepository(session)
            user_config = await user_config_repo.get_effective_config(user_id)

            recording_repo = RecordingRepository(session)

            for meeting in meetings:
                try:
                    meeting_id = meeting.get("uuid", meeting.get("id", ""))
                    display_name = meeting.get("topic", "Untitled")
                    start_time_str = meeting.get("start_time", "")
                    duration = meeting.get("duration", 0) * 60  # Zoom API returns minutes, we store seconds

                    if not start_time_str:
                        logger.info(f"Skipped: no start_time | {format_details(meeting=meeting_id)}")
                        continue

                    if start_time_str.endswith("Z"):
                        start_time_str = start_time_str[:-1] + "+00:00"
                    start_time = datetime.fromisoformat(start_time_str)

                    meeting_zoom_api = ZoomAPI(zoom_config)
                    video_file = _get_best_video_file(meeting.get("recording_files") or [])
                    (
                        meeting_details,
                        download_access_token,
                        zoom_processing_incomplete,
                    ) = await _fetch_zoom_recording_details(meeting_zoom_api, meeting_id)

                    source_metadata = _build_zoom_metadata(
                        meeting,
                        video_file,
                        download_access_token,
                        meeting_details,
                        zoom_processing_incomplete,
                        credentials,
                    )

                    video_file_size = video_file.get("file_size") if video_file else 0
                    matched_template = _find_matching_template(display_name, source_id, templates)
                    is_blank = _determine_blank_status(duration, video_file_size, zoom_processing_incomplete)

                    _recording, is_new = await recording_repo.create_or_update(
                        user_id=user_id,
                        input_source_id=source_id,
                        display_name=display_name,
                        start_time=start_time,
                        duration=duration,
                        source_type=SourceType.ZOOM,
                        source_key=meeting_id,
                        source_metadata=source_metadata,
                        user_config=user_config,
                        video_file_size=video_file_size,
                        is_mapped=matched_template is not None,
                        template_id=matched_template.id if matched_template else None,
                        blank_record=is_blank,
                        source_processing_incomplete=zoom_processing_incomplete,
                    )

                    if is_new:
                        saved_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    logger.warning(f"Failed to save recording | {format_details(meeting=meeting_id, error=str(e))}")
                    continue

            logger.info(
                f"Synced recordings | {format_details(source=source_id, total=saved_count + updated_count, new=saved_count, updated=updated_count)}"
            )

        except Exception as e:
            logger.error(f"Zoom sync failed | {format_details(source=source_id, error=str(e))}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    elif source.source_type == "VIDEO_URL":
        try:
            result = await _sync_video_url_source(
                source,
                session,
                user_id,
            )
            saved_count = result.get("saved", 0)
            updated_count = result.get("updated", 0)
            meetings = [None] * result.get("found", 0)  # placeholder for count
        except Exception as e:
            logger.error(f"VIDEO_URL sync failed | {format_details(source=source_id, error=str(e))}", exc_info=True)
            return {"status": "error", "error": str(e)}

    elif source.source_type == "YANDEX_DISK":
        try:
            result = await _sync_yandex_disk_source(
                source,
                credentials,
                session,
                user_id,
            )
            saved_count = result.get("saved", 0)
            updated_count = result.get("updated", 0)
            meetings = [None] * result.get("found", 0)
        except Exception as e:
            logger.error(f"Yandex Disk sync failed | {format_details(source=source_id, error=str(e))}", exc_info=True)
            return {"status": "error", "error": str(e)}

    elif source.source_type == "LOCAL":
        # LOCAL sources don't need sync
        pass

    else:
        return {
            "status": "error",
            "error": f"Unknown source type: {source.source_type}",
        }

    await repo.update_last_sync(source)

    return {
        "status": "success",
        "recordings_found": len(meetings),
        "recordings_saved": saved_count,
        "recordings_updated": updated_count,
    }


async def _sync_video_url_source(
    source,
    session: AsyncSession,
    user_id: str,
) -> dict:
    """Sync recordings from a VIDEO_URL source (yt-dlp: YouTube, VK, Rutube, etc.)."""
    from api.schemas.template.source_config import VideoUrlSourceConfig
    from video_download_module.platforms.ytdlp.metadata import (
        detect_platform,
        extract_playlist_entries,
        extract_video_info,
    )

    config = VideoUrlSourceConfig(**(source.config or {}))
    platform = config.video_platform or detect_platform(config.url)

    template_repo = RecordingTemplateRepository(session)
    templates = await template_repo.find_active_by_user(user_id)
    user_config_repo = UserConfigRepository(session)
    user_config = await user_config_repo.get_effective_config(user_id)
    recording_repo = RecordingRepository(session)

    saved_count = 0
    updated_count = 0

    if config.is_playlist:
        entries = await extract_playlist_entries(config.url)
    else:
        info = await extract_video_info(config.url)
        entries = [info]

    for entry in entries:
        try:
            video_id = entry.get("id", "")
            title = entry.get("title", "Unknown")
            duration = entry.get("duration") or 0
            video_url = entry.get("url") or entry.get("webpage_url", config.url)

            source_key = f"{platform}:{video_id}" if video_id else video_url

            source_metadata = {
                "url": video_url,
                "platform": platform,
                "video_id": video_id,
                "title": title,
                "duration": duration,
                "thumbnail": entry.get("thumbnail"),
                "uploader": entry.get("uploader"),
                "upload_date": entry.get("upload_date"),
                "quality": config.quality,
                "format_preference": config.format_preference,
            }

            matched_template = _find_matching_template(title, source.id, templates)

            _recording, is_new = await recording_repo.create_or_update(
                user_id=user_id,
                input_source_id=source.id,
                display_name=title,
                start_time=datetime.now(UTC),
                duration=duration,
                source_type=SourceType.EXTERNAL_URL,
                source_key=source_key,
                source_metadata=source_metadata,
                user_config=user_config,
                is_mapped=matched_template is not None,
                template_id=matched_template.id if matched_template else None,
            )

            if is_new:
                saved_count += 1
            else:
                updated_count += 1

        except Exception as e:
            logger.warning(
                f"Failed to save video entry | {format_details(video_id=entry.get('id', '?'), error=str(e))}"
            )
            continue

    logger.info(
        f"VIDEO_URL sync | {format_details(source=source.id, found=len(entries), saved=saved_count, updated=updated_count)}"
    )
    return {"found": len(entries), "saved": saved_count, "updated": updated_count}


async def _sync_yandex_disk_source(
    source,
    credentials: dict,
    session: AsyncSession,
    user_id: str,
) -> dict:
    """Sync recordings from a Yandex Disk source (folder listing or public link)."""
    from api.schemas.template.source_config import YandexDiskSourceConfig
    from yandex_disk_module.client import YandexDiskClient

    config = YandexDiskSourceConfig(**(source.config or {}))
    oauth_token = credentials.get("oauth_token") if credentials else None
    client = YandexDiskClient(oauth_token=oauth_token)

    template_repo = RecordingTemplateRepository(session)
    templates = await template_repo.find_active_by_user(user_id)
    user_config_repo = UserConfigRepository(session)
    user_config = await user_config_repo.get_effective_config(user_id)
    recording_repo = RecordingRepository(session)

    # Collect video files from Yandex Disk
    video_files: list[dict] = []

    if config.public_url:
        video_files = await client.list_public_video_files(
            public_key=config.public_url,
            file_pattern=config.file_pattern,
            recursive=config.recursive,
        )
    else:
        if not oauth_token:
            raise ValueError("Yandex Disk folder sync requires OAuth token in credentials")
        if not config.folder_path:
            raise ValueError("Yandex Disk folder sync requires folder_path in config")
        video_files = await client.list_video_files(
            folder_path=config.folder_path,
            recursive=config.recursive,
            file_pattern=config.file_pattern,
        )

    saved_count = 0
    updated_count = 0

    for file_info in video_files:
        try:
            file_path = file_info.get("path", "")
            file_name = file_info.get("name", "Unknown")
            file_size = file_info.get("size", 0)

            source_key = f"yadisk:{file_path}" if file_path else file_name

            download_method = "public" if config.public_url else "api"
            source_metadata = {
                "path": file_path,
                "name": file_name,
                "size": file_size,
                "mime_type": file_info.get("mime_type"),
                "download_method": download_method,
                "public_key": config.public_url,
                "modified": file_info.get("modified"),
            }

            matched_template = _find_matching_template(file_name, source.id, templates)

            modified_str = file_info.get("modified")
            if modified_str:
                try:
                    start_time = datetime.fromisoformat(modified_str)
                except (ValueError, TypeError):
                    start_time = datetime.now(UTC)
            else:
                start_time = datetime.now(UTC)

            _recording, is_new = await recording_repo.create_or_update(
                user_id=user_id,
                input_source_id=source.id,
                display_name=file_name,
                start_time=start_time,
                duration=0,
                source_type=SourceType.YANDEX_DISK,
                source_key=source_key,
                source_metadata=source_metadata,
                user_config=user_config,
                is_mapped=matched_template is not None,
                template_id=matched_template.id if matched_template else None,
            )

            if is_new:
                saved_count += 1
            else:
                updated_count += 1

        except Exception as e:
            logger.warning(
                f"Failed to save Yandex Disk file | {format_details(path=file_info.get('path', '?'), error=str(e))}"
            )
            continue

    logger.info(
        f"Yandex Disk sync | {format_details(source=source.id, found=len(video_files), saved=saved_count, updated=updated_count)}"
    )
    return {"found": len(video_files), "saved": saved_count, "updated": updated_count}


def _normalize_string(s: str, case_sensitive: bool) -> str:
    """Normalize string for comparison."""
    return s.strip() if case_sensitive else s.lower().strip()


def _check_source_filter(source_id: int, template_source_ids: list) -> bool:
    """Check if source_id matches template filter."""
    return not template_source_ids or source_id in template_source_ids


def _check_exclude_items(items: list | None, display_name: str, case_sensitive: bool, use_regex: bool = False) -> bool:
    """Check if any exclude item matches (keywords or patterns)."""
    if not items:
        return False

    for item in items:
        if not isinstance(item, str):
            continue

        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                if re.search(item, display_name, flags):
                    return True
            except re.error as e:
                logger.warning(f"Invalid regex pattern | {format_details(pattern=item, error=str(e))}")
        else:
            item_compare = _normalize_string(item, case_sensitive)
            display_compare = _normalize_string(display_name, case_sensitive)
            if item_compare in display_compare:
                return True

    return False


def _check_match_items(
    items: list | None, display_name: str, case_sensitive: bool, exact: bool = False, use_regex: bool = False
) -> bool:
    """Check if any match item matches (exact/keywords/patterns)."""
    if not items:
        return False

    display_compare = _normalize_string(display_name, case_sensitive)

    for item in items:
        if not isinstance(item, str):
            continue

        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                if re.search(item, display_name, flags):
                    return True
            except re.error as e:
                logger.warning(f"Invalid regex pattern | {format_details(pattern=item, error=str(e))}")
        elif exact:
            item_compare = _normalize_string(item, case_sensitive)
            if item_compare == display_compare:
                return True
        else:
            item_compare = _normalize_string(item, case_sensitive)
            if item_compare in display_compare:
                return True

    return False


def _find_matching_template(display_name: str, source_id: int, templates: list):
    """Find first matching template using first-match strategy."""
    if not templates:
        return None

    for template in templates:
        matching_rules = template.matching_rules or {}
        case_sensitive = matching_rules.get("case_sensitive", False)

        if not _check_source_filter(source_id, matching_rules.get("source_ids") or []):
            continue

        if _check_exclude_items(matching_rules.get("exclude_keywords"), display_name, case_sensitive):
            continue

        if _check_exclude_items(matching_rules.get("exclude_patterns"), display_name, case_sensitive, use_regex=True):
            continue

        if _check_match_items(matching_rules.get("exact_matches"), display_name, case_sensitive, exact=True):
            logger.debug(f"Matched template | {format_details(source=source_id, template=template.id, match='exact')}")
            return template

        if _check_match_items(matching_rules.get("keywords"), display_name, case_sensitive):
            logger.debug(
                f"Matched template | {format_details(source=source_id, template=template.id, match='keyword')}"
            )
            return template

        if _check_match_items(matching_rules.get("patterns"), display_name, case_sensitive, use_regex=True):
            logger.debug(
                f"Matched template | {format_details(source=source_id, template=template.id, match='pattern')}"
            )
            return template

    return None


SOURCE_SORT_FIELDS = {"created_at", "updated_at", "name", "last_sync_at"}


@router.get("", response_model=SourceListResponse)
async def list_sources(
    search: str | None = Query(None, description="Search substring in source name (case-insensitive)"),
    active_only: bool = False,
    platform: str | None = Query(None, description="Filter by source type (e.g. zoom, google_drive)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """Get paginated list of user's input sources."""
    repo = InputSourceRepository(session)

    if active_only:
        sources = await repo.find_active_by_user(current_user.id)
    else:
        sources = await repo.find_by_user(current_user.id)

    # Apply search filter
    if search:
        search_lower = search.lower()
        sources = [s for s in sources if search_lower in s.name.lower()]

    # Apply platform filter (case-insensitive)
    if platform:
        platform_upper = platform.upper()
        sources = [s for s in sources if s.source_type.upper() == platform_upper]

    items, total, total_pages = paginate_list(sources, page, per_page, sort_by, sort_order, SOURCE_SORT_FIELDS)

    return SourceListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.post("", response_model=InputSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    data: InputSourceCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Create new input source.

    Security:
        - Validates credential ownership before creation
    """
    from api.services.resource_access_validator import ResourceAccessValidator

    repo = InputSourceRepository(session)

    source_type = data.platform.upper()

    # Validate credential ownership
    if data.credential_id:
        validator = ResourceAccessValidator(session)
        await validator.validate_credential_access(
            data.credential_id,
            current_user.id,
            error_detail=f"Cannot create source: credential {data.credential_id} not found or access denied",
        )

    duplicate = await repo.find_duplicate(
        user_id=current_user.id,
        name=data.name,
        source_type=source_type,
        credential_id=data.credential_id,
    )

    if duplicate:
        cred_part = f"credential_id {data.credential_id}" if data.credential_id else "no credential"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Source with name '{data.name}', type '{source_type}' and {cred_part} already exists",
        )

    source = await repo.create(
        user_id=current_user.id,
        name=data.name,
        source_type=source_type,
        credential_id=data.credential_id,
        config=data.config.model_dump(exclude_none=True) if data.config else None,
        description=data.description,
    )

    await session.commit()
    return source


@router.post("/bulk/sync", response_model=BulkSyncTaskResponse)
async def bulk_sync_sources(
    data: BulkSyncRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Bulk sync multiple sources (async via Celery).

    Args:
        data: Request with source_ids, from_date, to_date

    Returns:
        task_id for tracking progress via GET /api/v1/tasks/{task_id}
    """
    # Validate that all sources exist and belong to the user
    repo = InputSourceRepository(session)
    invalid_sources = []
    source_names = []

    for source_id in data.source_ids:
        source = await repo.find_by_id(source_id, current_user.id)
        if not source:
            invalid_sources.append(source_id)
        else:
            source_names.append(source.name)

    if invalid_sources:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sources not found: {invalid_sources}")

    # Start Celery task
    from api.tasks.sync_tasks import bulk_sync_sources_task

    task = bulk_sync_sources_task.apply_async(
        kwargs={
            "source_ids": data.source_ids,
            "user_id": current_user.id,
            "from_date": data.from_date,
            "to_date": data.to_date,
        }
    )

    logger.info(
        f"Started batch sync task | {format_details(task=short_task_id(task.id), sources=len(data.source_ids), user=short_user_id(current_user.id))}"
    )

    return BulkSyncTaskResponse(
        task_id=task.id,
        status="queued",
        message=f"Batch sync task started for {len(data.source_ids)} sources",
        source_ids=data.source_ids,
        source_names=source_names,
    )


@router.get("/{source_id}", response_model=InputSourceResponse)
async def get_source(
    source_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """Get input source by ID."""
    repo = InputSourceRepository(session)
    source = await repo.find_by_id(source_id, current_user.id)

    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found")

    return source


@router.patch("/{source_id}", response_model=InputSourceResponse)
async def update_source(
    source_id: int,
    data: InputSourceUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Update input source.

    Security:
        - Validates source ownership
        - Validates credential ownership if credential_id is being updated
    """
    from api.services.resource_access_validator import ResourceAccessValidator

    repo = InputSourceRepository(session)
    source = await repo.find_by_id(source_id, current_user.id)

    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found")

    # Validate credential ownership if credential_id is being updated
    if data.credential_id is not None:
        validator = ResourceAccessValidator(session)
        await validator.validate_credential_for_update(
            data.credential_id, current_user.id, resource_name="input source"
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(source, field, value)

    await repo.update(source)
    await session.commit()

    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """Delete input source."""
    repo = InputSourceRepository(session)
    source = await repo.find_by_id(source_id, current_user.id)

    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found")

    await repo.delete(source)
    await session.commit()


@router.post("/{source_id}/sync", response_model=SourceSyncTaskResponse)
async def sync_source(
    source_id: int,
    from_date: str = "2025-01-01",
    to_date: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Sync recordings from one source (async via Celery).

    Args:
        source_id: Source ID
        from_date: Start date in format YYYY-MM-DD
        to_date: End date in format YYYY-MM-DD (optional)

    Returns:
        task_id for tracking progress via GET /api/v1/tasks/{task_id}
    """
    # Validate that source exists and belongs to the user
    repo = InputSourceRepository(session)
    source = await repo.find_by_id(source_id, current_user.id)

    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source {source_id} not found")

    if not source.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source is not active")

    # Start Celery task
    from api.tasks.sync_tasks import sync_single_source_task

    task = sync_single_source_task.apply_async(
        kwargs={
            "source_id": source_id,
            "user_id": current_user.id,
            "from_date": from_date,
            "to_date": to_date,
        }
    )

    logger.info(
        f"Started sync task | {format_details(task=short_task_id(task.id), source=source_id, user=short_user_id(current_user.id))}"
    )

    return SourceSyncTaskResponse(
        task_id=task.id,
        status="queued",
        message=f"Sync task started for source {source_id}",
        source_id=source_id,
        source_name=source.name,
    )
