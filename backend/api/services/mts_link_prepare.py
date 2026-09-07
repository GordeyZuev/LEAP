"""MTS Link prepare-before-run: short ping, order conversion, set pending status."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from api.helpers.blank_record import positive_duration_seconds
from api.mts_link_api import (
    CONVERSION_FAILED_STATES,
    MtsLinkAPI,
    MtsLinkAPIError,
    MtsLinkAuthenticationError,
    MtsLinkConversionBusyError,
    MtsLinkResponseError,
    conversion_busy_fields,
    conversion_job_state,
    conversion_progress,
    pick_active_conversion,
    prefer_conversion_job,
    unwrap_conversion_jobs,
)
from database.models import RecordingModel
from logger import format_details, get_logger
from models.recording import ProcessingStatus, SourceType

logger = get_logger()

_PREPARE_SKIP_TTL_SECONDS = 60
_TRANSIENT_RETRY_DELAY_SECONDS = 5
_MTS_PREPARE_STATUSES = frozenset(
    {
        ProcessingStatus.INITIALIZED,
        ProcessingStatus.SKIPPED,
        ProcessingStatus.PENDING_SOURCE,
        ProcessingStatus.PENDING_CONVERSION,
    }
)


class MtsPrepareOutcome(StrEnum):
    READY = "ready"
    ASSEMBLING = "assembling"
    CONVERTING = "converting"
    FAILED = "failed"


@dataclass
class MtsLinkPrepareResult:
    outcome: MtsPrepareOutcome
    conversion_id: Any | None = None
    conversion_state: str | None = None
    conversion_progress: int | None = None
    online_size: int | None = None
    download_url: str | None = None
    error: str | None = None


def recording_needs_mts_prepare(recording: RecordingModel) -> bool:
    """True when this recording should run the MTS prepare ping before pipeline."""
    if recording.local_video_path:
        return False
    if recording.source is None or recording.source.source_type != SourceType.MTS_LINK:
        return False
    return recording.status in _MTS_PREPARE_STATUSES


def should_skip_mts_prepare(recording: RecordingModel) -> bool:
    """Skip a redundant prepare when MP4 was confirmed moments ago or file exists."""
    if recording.local_video_path:
        return True
    meta = recording.source.meta if recording.source and isinstance(recording.source.meta, dict) else {}
    if meta.get("needs_mp4") is not False:
        return False
    checked_at = meta.get("mts_prepare_checked_at")
    if not checked_at:
        return False
    try:
        checked = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    return datetime.now(UTC) - checked < timedelta(seconds=_PREPARE_SKIP_TTL_SECONDS)


async def resolve_mts_link_context(session, recording: RecordingModel, user_id: str) -> tuple[int, MtsLinkAPI, dict]:
    """Credential id, API client, and conversion options from input source config."""
    from api.auth.encryption import get_encryption
    from api.repositories.auth_repos import UserCredentialRepository
    from api.repositories.template_repos import InputSourceRepository
    from models.mts_link_auth import create_mts_link_credentials

    input_source_id = recording.source.input_source_id if recording.source else None
    if not input_source_id:
        raise ValueError("MTS Link recording has no input source")

    source = await InputSourceRepository(session).find_by_id(input_source_id, user_id)
    if not source or not source.credential_id:
        raise ValueError("MTS Link source has no credential configured")

    credential = await UserCredentialRepository(session).get_by_id(source.credential_id)
    if not credential:
        raise ValueError(f"MTS Link credential {source.credential_id} not found")

    creds = create_mts_link_credentials(get_encryption().decrypt_credentials(credential.encrypted_data))
    config = source.config or {}
    api = MtsLinkAPI(api_token=creds.api_token, base_url=creds.base_url)
    options = {
        "conversion_quality": config.get("conversion_quality", "720"),
        "conversion_view": config.get("conversion_view", "none"),
    }
    return credential.id, api, options


async def prepare_mts_link_recording(session, recording: RecordingModel, user_id: str) -> MtsLinkPrepareResult:
    """Ping MTS Link and order or reuse conversion; does not set on_air."""
    if not recording_needs_mts_prepare(recording):
        return MtsLinkPrepareResult(outcome=MtsPrepareOutcome.READY)

    meta = recording.source.meta if recording.source and isinstance(recording.source.meta, dict) else {}
    mts_record_id = meta.get("mts_record_id")
    event_session_id = meta.get("event_session_id")
    if not mts_record_id or not event_session_id:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.FAILED,
            error="MTS Link metadata is incomplete (missing mts_record_id or event_session_id)",
        )

    credential_id, api, options = await resolve_mts_link_context(session, recording, user_id)

    for attempt in range(2):
        try:
            result = await _prepare_once(
                api,
                mts_record_id=mts_record_id,
                event_session_id=event_session_id,
                conversion_quality=options["conversion_quality"],
                conversion_view=options["conversion_view"],
                known_conversion_id=meta.get("conversion_id"),
                known_duration=meta.get("online_duration"),
            )
            await _apply_auth_side_effects(session, credential_id, result)
            return result
        except MtsLinkAuthenticationError as e:
            from api.repositories.auth_repos import UserCredentialRepository

            await UserCredentialRepository(session).set_needs_reauth(credential_id, True)
            return MtsLinkPrepareResult(outcome=MtsPrepareOutcome.FAILED, error=str(e))
        except MtsLinkAPIError as e:
            if attempt == 0 and _is_transient_error(e):
                await asyncio.sleep(_TRANSIENT_RETRY_DELAY_SECONDS)
                continue
            return MtsLinkPrepareResult(outcome=MtsPrepareOutcome.FAILED, error=str(e))

    return MtsLinkPrepareResult(outcome=MtsPrepareOutcome.FAILED, error="MTS Link prepare failed after retry")


async def _apply_auth_side_effects(session, credential_id: int, result: MtsLinkPrepareResult) -> None:
    if result.outcome == MtsPrepareOutcome.FAILED:
        return
    from api.repositories.auth_repos import UserCredentialRepository

    await UserCredentialRepository(session).set_needs_reauth(credential_id, False)


def _is_transient_error(exc: MtsLinkAPIError) -> bool:
    if isinstance(exc, MtsLinkResponseError):
        return exc.status_code >= 500
    return True


async def _prepare_once(
    api: MtsLinkAPI,
    *,
    mts_record_id: Any,
    event_session_id: Any,
    conversion_quality: str,
    conversion_view: str,
    known_conversion_id: Any | None = None,
    known_duration: Any | None = None,
) -> MtsLinkPrepareResult:
    ready_url = None
    try:
        ready_url = await api.get_ready_mp4_url(event_session_id, mts_record_id)
    except MtsLinkResponseError as e:
        if e.status_code != 404:
            raise
    if ready_url:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.READY,
            download_url=ready_url,
        )

    listed = await _fetch_active_conversion(api, mts_record_id)
    known = None
    if known_conversion_id:
        try:
            known = await _fetch_conversion_by_id(api, known_conversion_id)
        except MtsLinkAPIError:
            if listed is None:
                return MtsLinkPrepareResult(
                    outcome=MtsPrepareOutcome.CONVERTING,
                    conversion_id=known_conversion_id,
                    conversion_state="unknown",
                )
    active = prefer_conversion_job(listed, known)
    if active is not None:
        return _from_existing_job(active, online_size=None)

    found, online_size = await _fetch_online_size(api, mts_record_id)
    if not found:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.FAILED,
            error="MTS Link online recording was not found",
        )
    duration = await _resolve_online_duration(api, mts_record_id, known_duration)
    if duration is None and online_size == 0:
        return MtsLinkPrepareResult(outcome=MtsPrepareOutcome.ASSEMBLING, online_size=0)

    conversion = await _start_conversion(
        api,
        mts_record_id,
        quality=conversion_quality,
        view=conversion_view,
    )
    if conversion is None:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.CONVERTING,
            conversion_id=known_conversion_id,
            online_size=online_size,
            conversion_state="busy",
        )

    return _from_existing_job(conversion, online_size)


async def _fetch_online_size(api: MtsLinkAPI, mts_record_id: Any) -> tuple[bool, int]:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    records = await api.list_records(
        from_date="2000-01-01 00:00:00",
        to_date=f"{today} 23:59:59",
        record_id=int(mts_record_id),
        limit=1,
    )
    if records:
        return True, int(records[0].get("size") or 0)
    return False, 0


async def _resolve_online_duration(api: MtsLinkAPI, mts_record_id: Any, known: Any) -> float | None:
    """Same signal as sync: duration from fileSystem/file, not GET /records size."""
    parsed = positive_duration_seconds(known)
    if parsed is not None:
        return parsed
    try:
        payload = await api.get_file(mts_record_id)
    except MtsLinkAPIError:
        return None
    if not isinstance(payload, dict):
        return None
    return positive_duration_seconds(payload.get("duration"))


async def _fetch_conversion_by_id(api: MtsLinkAPI, conversion_id: Any) -> dict[str, Any] | None:
    try:
        return await api.get_conversion_status(conversion_id)
    except MtsLinkResponseError as e:
        if e.status_code == 404:
            return None
        raise


async def _list_conversions(api: MtsLinkAPI, *, is_uncompleted: bool) -> list[dict[str, Any]]:
    per_page = 500
    accumulated: list[dict[str, Any]] = []
    for page in range(1, 6):
        payload = await api.list_converted_records(
            from_date="2000-01-01",
            page=page,
            per_page=per_page,
            is_uncompleted=is_uncompleted,
        )
        items = unwrap_conversion_jobs(payload)
        accumulated.extend(items)
        if len(items) < per_page:
            break
    return accumulated


async def _fetch_active_conversion(api: MtsLinkAPI, mts_record_id: Any) -> dict[str, Any] | None:
    accumulated: list[dict[str, Any]] = []
    for is_uncompleted in (True, False):
        try:
            accumulated.extend(await _list_conversions(api, is_uncompleted=is_uncompleted))
        except MtsLinkAPIError as e:
            logger.debug(f"Converted-records list unavailable | {format_details(record=mts_record_id, error=str(e))}")
    return pick_active_conversion(accumulated, mts_record_id)


async def _start_conversion(
    api: MtsLinkAPI,
    mts_record_id: Any,
    *,
    quality: str,
    view: str,
) -> dict[str, Any] | None:
    try:
        conversion = await api.start_conversion(mts_record_id, quality=quality, view=view)
    except MtsLinkConversionBusyError as e:
        busy_id, _busy_record = conversion_busy_fields(e.payload)
        logger.info(
            f"MTS Link conversion busy | {format_details(record=mts_record_id, conversion=busy_id, detail=str(e))}"
        )
        if busy_id is not None:
            known = await _fetch_conversion_by_id(api, busy_id)
            if known is not None:
                return known
            return {"id": busy_id, "state": "busy"}
        return None

    logger.info(
        f"MTS Link conversion requested | {format_details(record=mts_record_id, conversion=conversion.get('id'), quality=quality)}"
    )
    return conversion


def _from_existing_job(job: dict[str, Any], online_size: int | None) -> MtsLinkPrepareResult:
    url = job.get("downloadUrl")
    state = conversion_job_state(job)
    if url:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.READY,
            conversion_id=job.get("id"),
            conversion_state=state or "completed",
            conversion_progress=conversion_progress(job) or 100,
            download_url=str(url),
            online_size=online_size,
        )
    return _conversion_result(job, online_size)


def _conversion_result(active: dict[str, Any], online_size: int | None) -> MtsLinkPrepareResult:
    conversion_id = active.get("id")
    state = conversion_job_state(active) or None
    progress = conversion_progress(active)
    if state == "completed" and progress is None:
        progress = 100
    if state in CONVERSION_FAILED_STATES:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.FAILED,
            conversion_id=conversion_id,
            conversion_state=state,
            conversion_progress=progress,
            online_size=online_size,
            error=f"MTS Link conversion {conversion_id} failed with state {state!r}",
        )
    # GET /records/conversions/{id} is often ``{state: completed}`` with no URL.
    if state == "completed":
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.READY,
            conversion_id=conversion_id,
            conversion_state=state,
            conversion_progress=progress,
            download_url=str(active["downloadUrl"]) if active.get("downloadUrl") else None,
            online_size=online_size,
        )
    return MtsLinkPrepareResult(
        outcome=MtsPrepareOutcome.CONVERTING,
        conversion_id=conversion_id,
        conversion_state=state,
        conversion_progress=progress,
        online_size=online_size,
    )


def apply_prepare_result(recording: RecordingModel, result: MtsLinkPrepareResult) -> None:
    """Persist status and source meta from prepare; never touches on_air."""
    if recording.source is None:
        return

    meta = dict(recording.source.meta or {})
    now_iso = datetime.now(UTC).isoformat()
    meta["mts_prepare_checked_at"] = now_iso

    if result.online_size is not None:
        meta["online_size"] = result.online_size

    if result.conversion_id is not None:
        meta["conversion_id"] = result.conversion_id
    if result.conversion_state is not None:
        meta["conversion_state"] = result.conversion_state
    if result.outcome == MtsPrepareOutcome.CONVERTING:
        if result.conversion_progress is not None:
            meta["conversion_progress"] = result.conversion_progress
    elif result.conversion_progress is not None:
        meta["conversion_progress"] = result.conversion_progress

    if result.outcome == MtsPrepareOutcome.READY:
        meta["needs_mp4"] = False
        meta["source_processing_incomplete"] = False
        if result.download_url:
            meta["download_url"] = result.download_url
        recording.failed = False
        recording.failed_reason = None
        recording.failed_at_stage = None
        recording.status = ProcessingStatus.INITIALIZED if recording.is_mapped else ProcessingStatus.SKIPPED
    elif result.outcome == MtsPrepareOutcome.ASSEMBLING:
        meta["needs_mp4"] = True
        meta["source_processing_incomplete"] = True
        recording.failed = False
        recording.failed_reason = None
        recording.failed_at_stage = None
        recording.status = ProcessingStatus.PENDING_SOURCE
    elif result.outcome == MtsPrepareOutcome.CONVERTING:
        meta["needs_mp4"] = True
        meta["source_processing_incomplete"] = False
        recording.failed = False
        recording.failed_reason = None
        recording.failed_at_stage = None
        recording.status = ProcessingStatus.PENDING_CONVERSION
    elif result.outcome == MtsPrepareOutcome.FAILED:
        meta["needs_mp4"] = True
        recording.failed = True
        recording.failed_at_stage = "download"
        recording.failed_reason = result.error or "MTS Link prepare failed"
        recording.status = ProcessingStatus.INITIALIZED if recording.is_mapped else ProcessingStatus.SKIPPED

    recording.source.meta = meta


def mts_prepare_response_fields(result: MtsLinkPrepareResult) -> dict[str, Any]:
    """Build the ``mts`` block for RecordingOperationResponse."""
    return {
        "outcome": result.outcome.value,
        "conversion_id": result.conversion_id,
        "conversion_state": result.conversion_state,
        "conversion_progress": result.conversion_progress,
        "online_size": result.online_size,
    }
