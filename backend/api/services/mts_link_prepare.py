"""MTS Link prepare-before-run: short ping, order conversion, set pending status."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from api.mts_link_api import (
    MtsLinkAPI,
    MtsLinkAPIError,
    MtsLinkAuthenticationError,
    MtsLinkConversionBusyError,
    pick_active_conversion,
    unwrap_conversion_jobs,
)
from database.models import RecordingModel
from logger import format_details, get_logger
from models.recording import ProcessingStatus, SourceType

logger = get_logger()

_PREPARE_SKIP_TTL_SECONDS = 60
_TRANSIENT_RETRY_DELAY_SECONDS = 5
_CONVERSION_FAILED_STATES = frozenset({"error", "failed", "fail", "canceled", "cancelled"})
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
    from api.mts_link_api import MtsLinkResponseError

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
) -> MtsLinkPrepareResult:
    online_size = await _fetch_online_size(api, mts_record_id)
    if online_size == 0:
        return MtsLinkPrepareResult(outcome=MtsPrepareOutcome.ASSEMBLING, online_size=0)

    ready_url = await api.get_ready_mp4_url(event_session_id)
    if ready_url:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.READY,
            online_size=online_size,
            download_url=ready_url,
        )

    active = await _fetch_active_conversion(api, mts_record_id)
    if active is not None:
        return _conversion_result(active, online_size)

    conversion_id = await _start_conversion(
        api,
        mts_record_id,
        quality=conversion_quality,
        view=conversion_view,
    )
    if conversion_id is None:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.CONVERTING,
            online_size=online_size,
            conversion_state="busy",
        )

    state, progress = await _conversion_state(api, conversion_id)
    if state in _CONVERSION_FAILED_STATES:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.FAILED,
            conversion_id=conversion_id,
            conversion_state=state,
            conversion_progress=progress,
            online_size=online_size,
            error=f"MTS Link conversion {conversion_id} failed with state {state!r}",
        )

    return MtsLinkPrepareResult(
        outcome=MtsPrepareOutcome.CONVERTING,
        conversion_id=conversion_id,
        conversion_state=state,
        conversion_progress=progress,
        online_size=online_size,
    )


async def _fetch_online_size(api: MtsLinkAPI, mts_record_id: Any) -> int:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    records = await api.list_records(from_date="2000-01-01", to_date=today, record_id=int(mts_record_id), limit=1)
    if records:
        return int(records[0].get("size") or 0)
    return 0


async def _fetch_active_conversion(api: MtsLinkAPI, mts_record_id: Any) -> dict[str, Any] | None:
    try:
        payload = await api.list_converted_records(page=1, per_page=50)
    except MtsLinkAPIError as e:
        logger.debug(f"Converted-records list unavailable | {format_details(record=mts_record_id, error=str(e))}")
        return None
    return pick_active_conversion(unwrap_conversion_jobs(payload), mts_record_id)


async def _start_conversion(
    api: MtsLinkAPI,
    mts_record_id: Any,
    *,
    quality: str,
    view: str,
) -> Any | None:
    try:
        conversion = await api.start_conversion(mts_record_id, quality=quality, view=view)
    except MtsLinkConversionBusyError as e:
        logger.info(f"MTS Link conversion busy | {format_details(record=mts_record_id, detail=str(e))}")
        return None

    conversion_id = conversion.get("id")
    logger.info(
        f"MTS Link conversion requested | {format_details(record=mts_record_id, conversion=conversion_id, quality=quality)}"
    )
    return conversion_id


async def _conversion_state(api: MtsLinkAPI, conversion_id: Any) -> tuple[str | None, int | None]:
    try:
        status = await api.get_conversion_status(conversion_id)
    except MtsLinkAPIError:
        return None, None
    state = str(status.get("state") or status.get("status") or "").lower() or None
    try:
        progress = int(status.get("progress") or 0)
    except (TypeError, ValueError):
        progress = None
    return state, progress


def _conversion_result(active: dict[str, Any], online_size: int) -> MtsLinkPrepareResult:
    conversion_id = active.get("id")
    state = str(active.get("state") or "").lower() or None
    try:
        progress = int(active.get("progress") or 0)
    except (TypeError, ValueError):
        progress = None
    if state in _CONVERSION_FAILED_STATES:
        return MtsLinkPrepareResult(
            outcome=MtsPrepareOutcome.FAILED,
            conversion_id=conversion_id,
            conversion_state=state,
            conversion_progress=progress,
            online_size=online_size,
            error=f"MTS Link conversion {conversion_id} failed with state {state!r}",
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
        meta["source_processing_incomplete"] = result.online_size == 0

    if result.conversion_id is not None:
        meta["conversion_id"] = result.conversion_id
    if result.conversion_state is not None:
        meta["conversion_state"] = result.conversion_state
    if result.conversion_progress is not None:
        meta["conversion_progress"] = result.conversion_progress

    if result.outcome == MtsPrepareOutcome.READY:
        meta["needs_mp4"] = False
        if result.download_url:
            meta["download_url"] = result.download_url
        recording.failed = False
        recording.failed_reason = None
        recording.failed_at_stage = None
        recording.status = ProcessingStatus.INITIALIZED if recording.is_mapped else ProcessingStatus.SKIPPED
    elif result.outcome == MtsPrepareOutcome.ASSEMBLING:
        meta["needs_mp4"] = True
        recording.failed = False
        recording.failed_reason = None
        recording.failed_at_stage = None
        recording.status = ProcessingStatus.PENDING_SOURCE
    elif result.outcome == MtsPrepareOutcome.CONVERTING:
        meta["needs_mp4"] = True
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
