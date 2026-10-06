"""Write provider spend. Callers that poll for a long time commit ``submitted`` on their own session."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from api.dependencies import get_async_session_maker
from api.repositories.resource_ledger_repo import ResourceLedgerRepository
from database.auth_models import ResourceLedgerModel
from logger import get_logger

logger = get_logger()

DEEPSEEK_SCAN_KEY = "backfill:deepseek:scan-complete"
IMPORT_CURSOR_KEY = "aai-import:cursor"
UNATTRIBUTED_LEDGER_USER = "unattributed"
_RECORDING_IN_URL = re.compile(r"recordings/(\d+)")


def attempt_idempotency_key(celery_task_id: str) -> str:
    return f"aai-attempt:{celery_task_id}"


def recording_id_from_audio_url(audio_url: str) -> int | None:
    """Recording id embedded in a storage key or presigned URL."""
    match = _RECORDING_IN_URL.search(unquote(audio_url))
    if match is None:
        return None
    return int(match.group(1))


_MAX_TRANSCRIPT_PAGES = 100


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def should_import_untracked(
    *,
    created: datetime | None,
    watermark: datetime | None,
    recording_id: int | None,
    pending_match: bool,
    estimate_at: datetime | None,
) -> bool:
    """Whether a provider transcript id missing from the ledger should be written.

    A pending attempt is the job we already meant to record. A recording whose
    segment_end estimate is at or after ``created`` already stands in for that
    historical run; a later transcript is a separate invoice. A transcript we
    cannot attach to a recording is imported only after the global estimate
    cutoff, so anonymous history is not added a second time.
    """
    if pending_match:
        return True
    if recording_id is not None:
        if estimate_at is None:
            return True
        if created is None:
            return False
        return _as_utc(created) > _as_utc(estimate_at)
    if created is None:
        return watermark is None
    return transcript_after_backfill(created, watermark)


def transcript_after_backfill(created: datetime, watermark: datetime | None) -> bool:
    """True when a provider transcript is newer than the historical estimate cutoff.

    Estimates have no AssemblyAI id. Importing older transcripts would count
    those minutes twice. A missing watermark means there is nothing to double.
    """
    if watermark is None:
        return True
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if watermark.tzinfo is None:
        watermark = watermark.replace(tzinfo=UTC)
    return created > watermark


def resume_transcript_id(
    open_submitted: str | None,
    attempt_job_id: str | None,
    attempt_status: str | None,
) -> str | None:
    """Job to poll instead of submitting a second AssemblyAI transcript.

    ``open_submitted`` is a ledger row still in ``submitted``. ``attempt_job_id``
    is the job this same Celery task already created, stamped on the stage timing
    before the long poll. A retry or a worker redelivery keeps that task id, so
    the stamp is still there after the row moves to ``completed`` (the save failed,
    or the process died). Polling it does not open a second invoice. ``failed``
    was not billed, so that attempt may submit again. A new task id has no stamp:
    the user asked for another transcription, including after reset.
    """
    if open_submitted:
        return open_submitted
    if not attempt_job_id or attempt_status == "failed":
        return None
    return attempt_job_id


class ResourceLedgerService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ResourceLedgerRepository(session)

    async def open_transcription_job_id(self, recording_id: int) -> str | None:
        return await self.repo.open_transcription_job_id(recording_id)

    async def open_attempt_job_id(self, celery_task_id: str) -> str | None:
        """Job id already stored for this Celery task, including before the timing stamp."""
        if not celery_task_id:
            return None
        row = await self.repo.get_by_idempotency(attempt_idempotency_key(celery_task_id))
        job_id = row.provider_job_id if row is not None else None
        return job_id if isinstance(job_id, str) and job_id else None

    async def attempt_audio_url(self, celery_task_id: str) -> str | None:
        """Audio URL stored before POST, when the provider id never came back."""
        if not celery_task_id:
            return None
        row = await self.repo.get_by_idempotency(attempt_idempotency_key(celery_task_id))
        if row is None or row.provider_job_id:
            return None
        details = row.details if isinstance(row.details, dict) else {}
        audio_url = details.get("audio_url")
        return audio_url if isinstance(audio_url, str) and audio_url else None

    async def prepare_transcription_attempt(
        self,
        *,
        user_id: str,
        recording_id: int,
        celery_task_id: str,
        audio_url: str,
        model: str | None,
        language: str | None,
        speech_models: list[str] | None,
    ) -> None:
        """Commit the audio URL before POST so a lost response can still be matched."""
        if not celery_task_id:
            return
        key = attempt_idempotency_key(celery_task_id)
        row = await self.repo.get_by_idempotency(key)
        now = datetime.now(UTC)
        if row is None:
            self.repo.add(
                ResourceLedgerModel(
                    user_id=user_id,
                    recording_id=recording_id,
                    provider="assemblyai",
                    operation="transcribe",
                    provider_job_id=None,
                    status="submitted",
                    model=model,
                    occurred_at=now,
                    idempotency_key=key,
                    details={"language": language, "speech_models": speech_models or [], "audio_url": audio_url},
                    created_at=now,
                )
            )
            await self.session.flush()
            return
        if row.provider_job_id:
            return
        raw_details = row.details if isinstance(row.details, dict) else {}
        details = {str(key_name): value for key_name, value in raw_details.items()}
        details["audio_url"] = audio_url
        row.details = details
        await self.session.flush()

    async def mark_transcription_submitted(
        self,
        *,
        user_id: str,
        recording_id: int | None,
        provider_job_id: str,
        model: str | None,
        language: str | None,
        speech_models: list[str] | None,
        attempt_key: str | None = None,
    ) -> None:
        existing = await self.repo.get_by_job_id(provider_job_id)
        if existing is not None:
            return
        if attempt_key:
            attempt = await self.repo.get_by_idempotency(attempt_key)
            if attempt is not None and attempt.status != "completed":
                raw_details = attempt.details if isinstance(attempt.details, dict) else {}
                details = {str(key_name): value for key_name, value in raw_details.items()}
                details.pop("audio_url", None)
                attempt.provider_job_id = provider_job_id
                attempt.status = "submitted"
                attempt.details = details
                if model:
                    attempt.model = model
                await self.session.flush()
                return
        now = datetime.now(UTC)
        self.repo.add(
            ResourceLedgerModel(
                user_id=user_id,
                recording_id=recording_id,
                provider="assemblyai",
                operation="transcribe",
                provider_job_id=provider_job_id,
                status="submitted",
                model=model,
                occurred_at=now,
                idempotency_key=f"aai:{provider_job_id}",
                details={"language": language, "speech_models": speech_models or []},
                created_at=now,
            )
        )
        await self.session.flush()

    async def mark_transcription_completed(
        self,
        *,
        user_id: str,
        recording_id: int | None,
        provider_job_id: str,
        audio_seconds: float | None,
        model: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Close a transcript. Without ``audio_seconds`` the row stays ``submitted`` for a later fetch."""
        if audio_seconds is None:
            return
        row = await self.repo.get_by_job_id(provider_job_id)
        now = occurred_at or datetime.now(UTC)
        if row is None:
            self.repo.add(
                ResourceLedgerModel(
                    user_id=user_id,
                    recording_id=recording_id,
                    provider="assemblyai",
                    operation="transcribe",
                    provider_job_id=provider_job_id,
                    status="completed",
                    audio_seconds=audio_seconds,
                    model=model,
                    occurred_at=now,
                    idempotency_key=f"aai:{provider_job_id}",
                    details={"basis": "audio_duration"},
                    created_at=datetime.now(UTC),
                )
            )
            await self.session.flush()
            return
        raw_details = row.details if isinstance(row.details, dict) else {}
        details = {str(key): value for key, value in raw_details.items()}
        details.pop("audio_url", None)
        details["basis"] = "audio_duration"
        row.status = "completed"
        row.audio_seconds = audio_seconds
        if occurred_at is not None:
            row.occurred_at = occurred_at
        if model:
            row.model = model
        row.details = details
        await self.session.flush()

    async def mark_transcription_failed(self, *, provider_job_id: str) -> None:
        row = await self.repo.get_by_job_id(provider_job_id)
        if row is None:
            return
        row.status = "failed"
        row.audio_seconds = None
        await self.session.flush()

    async def record_topic_usage(
        self,
        *,
        user_id: str,
        recording_id: int | None,
        model: str | None,
        usage: dict[str, Any],
        basis: str = "usage",
        occurred_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """One DeepSeek HTTP call. A retry that calls the API again is a new row."""
        now = occurred_at or datetime.now(UTC)
        self.repo.add(
            ResourceLedgerModel(
                user_id=user_id,
                recording_id=recording_id,
                provider="deepseek",
                operation="extract_topics",
                status="completed",
                prompt_tokens=_token(usage, "prompt_tokens"),
                completion_tokens=_token(usage, "completion_tokens"),
                cache_hit_tokens=_token(usage, "prompt_cache_hit_tokens"),
                cache_miss_tokens=_token(usage, "prompt_cache_miss_tokens"),
                model=model,
                occurred_at=now,
                idempotency_key=idempotency_key or f"deepseek:{ULID()}",
                details={"basis": basis},
                created_at=datetime.now(UTC),
            )
        )
        await self.session.flush()

    async def record_storage_snapshot(self, *, user_id: str, stored_bytes: int, hour: datetime) -> None:
        await self.repo.insert_ignore(
            {
                "id": str(ULID()),
                "user_id": user_id,
                "recording_id": None,
                "provider": "storage",
                "operation": "storage_snapshot",
                "provider_job_id": None,
                "status": "completed",
                "audio_seconds": None,
                "stored_bytes": stored_bytes,
                "model": None,
                "occurred_at": hour,
                "idempotency_key": f"storage:{user_id}:{hour.strftime('%Y-%m-%dT%H')}",
                "details": {"basis": "prefix_bytes"},
                "created_at": datetime.now(UTC),
            }
        )


class AssemblyAILedgerHooks:
    """Commits ledger rows on a session that is not the Celery task session."""

    def __init__(
        self,
        *,
        user_id: str,
        recording_id: int,
        model: str | None,
        language: str | None,
        speech_models: list[str] | None,
        celery_task_id: str | None = None,
    ):
        self.user_id = user_id
        self.recording_id = recording_id
        self.model = model
        self.language = language
        self.speech_models = speech_models
        self.celery_task_id = celery_task_id

    async def prepare(self, audio_url: str) -> None:
        if not self.celery_task_id:
            return
        await self._commit(
            lambda svc: svc.prepare_transcription_attempt(
                user_id=self.user_id,
                recording_id=self.recording_id,
                celery_task_id=self.celery_task_id,
                audio_url=audio_url,
                model=self.model,
                language=self.language,
                speech_models=self.speech_models,
            )
        )

    async def submitted(self, transcript_id: str) -> None:
        attempt_key = attempt_idempotency_key(self.celery_task_id) if self.celery_task_id else None
        await self._commit(
            lambda svc: svc.mark_transcription_submitted(
                user_id=self.user_id,
                recording_id=self.recording_id,
                provider_job_id=transcript_id,
                model=self.model,
                language=self.language,
                speech_models=self.speech_models,
                attempt_key=attempt_key,
            )
        )

    async def completed(self, transcript_id: str, audio_seconds: float | None, model: str | None = None) -> None:
        await self._commit(
            lambda svc: svc.mark_transcription_completed(
                user_id=self.user_id,
                recording_id=self.recording_id,
                provider_job_id=transcript_id,
                audio_seconds=audio_seconds,
                model=model,
            )
        )

    async def failed(self, transcript_id: str) -> None:
        await self._commit(lambda svc: svc.mark_transcription_failed(provider_job_id=transcript_id))

    async def _commit(self, write) -> None:
        maker = get_async_session_maker()
        async with maker() as session:
            await write(ResourceLedgerService(session))
            await session.commit()


class RecordingAttemptHooks:
    """Remember the AssemblyAI job on this Celery attempt, then write the ledger.

    The stage-timing stamp is committed on the task session before the ledger
    write and before the poll. A later run of the same task id can poll that job
    even when the ledger commit failed or the row is already ``completed``.
    """

    def __init__(self, inner: AssemblyAILedgerHooks, session: AsyncSession, timing: Any, celery_task_id: str):
        self.inner = inner
        self.session = session
        self.timing = timing
        self.celery_task_id = celery_task_id

    async def preparing(self, audio_url: str) -> None:
        await self.inner.prepare(audio_url)

    async def submitted(self, transcript_id: str) -> None:
        if self.celery_task_id:
            meta = dict(self.timing.meta or {})
            meta["provider_job_id"] = transcript_id
            meta["celery_task_id"] = self.celery_task_id
            self.timing.meta = meta
            await self.session.commit()
        await self.inner.submitted(transcript_id)

    async def completed(self, transcript_id: str, audio_seconds: float | None, model: str | None = None) -> None:
        await self.inner.completed(transcript_id, audio_seconds, model)

    async def failed(self, transcript_id: str) -> None:
        await self.inner.failed(transcript_id)


async def commit_topic_usage(
    *,
    user_id: str,
    recording_id: int,
    model: str | None,
    usage: dict[str, Any],
) -> None:
    """Commit DeepSeek tokens before JSON parsing, on a session the task cannot roll back."""
    maker = get_async_session_maker()
    async with maker() as session:
        await ResourceLedgerService(session).record_topic_usage(
            user_id=user_id,
            recording_id=recording_id,
            model=model,
            usage=usage,
        )
        await session.commit()


async def backfill_topic_tokens(session: AsyncSession) -> None:
    """Copy ``usage`` from live extracted.json versions. Missing files stay missing."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from database.models import RecordingModel
    from file_storage.factory import get_storage_backend
    from transcription_module.manager import get_transcription_manager

    if await ResourceLedgerRepository(session).has_idempotency_key(DEEPSEEK_SCAN_KEY):
        return

    result = await session.execute(select(RecordingModel).options(selectinload(RecordingModel.owner)))
    recordings = list(result.scalars().all())
    storage = get_storage_backend()
    manager = get_transcription_manager()
    service = ResourceLedgerService(session)
    had_error = False

    for recording in recordings:
        owner = recording.owner
        if owner is None:
            continue
        key = manager._extracted_key(recording.id, owner.user_slug)
        try:
            if not await storage.exists(key):
                continue
            payload = json.loads(await storage.load(key))
        except Exception as exc:
            had_error = True
            logger.warning(f"Skipped topic backfill | rec={recording.id} | error={exc}")
            continue
        versions = payload.get("versions") if isinstance(payload, dict) else None
        if not isinstance(versions, list):
            continue
        for version in versions:
            if not isinstance(version, dict):
                continue
            meta = version.get("_metadata") if isinstance(version.get("_metadata"), dict) else {}
            tokens = meta.get("tokens") if isinstance(meta, dict) else None
            if not isinstance(tokens, dict) or not tokens:
                continue
            version_id = str(version.get("id") or "")
            if not version_id or not isinstance(recording.user_id, str):
                continue
            idempotency_key = f"backfill:topics:{recording.id}:{version_id}"
            if await service.repo.has_idempotency_key(idempotency_key):
                continue
            await service.record_topic_usage(
                user_id=recording.user_id,
                recording_id=recording.id,
                model=version.get("model") if isinstance(version.get("model"), str) else None,
                usage=tokens,
                basis="extracted_json",
                occurred_at=_version_time(version.get("created_at")),
                idempotency_key=idempotency_key,
            )

    if had_error:
        return
    await service.repo.insert_ignore(
        {
            "id": str(ULID()),
            "user_id": "system",
            "recording_id": None,
            "provider": "deepseek",
            "operation": "extract_topics",
            "provider_job_id": None,
            "status": "completed",
            "model": None,
            "occurred_at": datetime.now(UTC),
            "idempotency_key": DEEPSEEK_SCAN_KEY,
            "details": {"basis": "scan_complete"},
            "created_at": datetime.now(UTC),
        }
    )


def parse_provider_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


async def _attribute_transcript(session: AsyncSession, audio_url: str) -> tuple[str, int | None]:
    recording_id = recording_id_from_audio_url(audio_url) if audio_url else None
    if recording_id is None:
        return UNATTRIBUTED_LEDGER_USER, None
    from database.models import RecordingModel

    recording = await session.get(RecordingModel, recording_id)
    user_id = getattr(recording, "user_id", None) if recording is not None else None
    if isinstance(user_id, str) and user_id:
        return user_id, recording_id
    return UNATTRIBUTED_LEDGER_USER, recording_id


async def import_untracked_transcripts(session: AsyncSession, source: Any) -> int:
    """Record completed AssemblyAI jobs whose id never landed in the ledger.

    The list is newest-first. Each run reads the head until a page is already
    fully recorded, and continues a saved older page so a long history is not
    stuck behind the page cap. A historical estimate blocks only its recording,
    and only transcripts created at or before that estimate.
    """
    ledger = ResourceLedgerService(session)
    watermark = await ledger.repo.segment_end_watermark()
    estimates = await ledger.repo.segment_end_by_recording()
    cursor = await _import_cursor(ledger)
    imported = await _scan_transcript_pages(
        session,
        ledger,
        source,
        watermark,
        estimates,
        page_url=None,
        stop_when_known=True,
        save_cursor=cursor is None,
    )
    if cursor:
        imported += await _scan_transcript_pages(
            session,
            ledger,
            source,
            watermark,
            estimates,
            page_url=cursor,
            stop_when_known=False,
            save_cursor=True,
        )
    return imported


async def _scan_transcript_pages(
    session: AsyncSession,
    ledger: ResourceLedgerService,
    source: Any,
    watermark: datetime | None,
    estimates: dict[int, datetime],
    *,
    page_url: str | None,
    stop_when_known: bool,
    save_cursor: bool,
) -> int:
    imported = 0
    reached_end = False
    list_failed = False
    resume_from: str | None = None
    for _page in range(_MAX_TRANSCRIPT_PAGES):
        try:
            payload = await source.list_transcripts(page_url=page_url)
        except Exception as exc:
            logger.error(f"AssemblyAI import list failed | error={exc}")
            list_failed = True
            break
        if not isinstance(payload, dict):
            reached_end = True
            break
        items = payload.get("transcripts")
        if not isinstance(items, list) or not items:
            reached_end = True
            break
        page_ids = [job_id for item in items if isinstance(item, dict) and isinstance(job_id := item.get("id"), str)]
        known_ids = await ledger.repo.existing_job_ids(page_ids)
        if stop_when_known and page_ids and all(job_id in known_ids for job_id in page_ids):
            reached_end = True
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = item.get("id")
            if not isinstance(job_id, str) or not job_id or job_id in known_ids:
                continue
            created = parse_provider_time(item.get("created"))
            audio_url = item.get("audio_url") if isinstance(item.get("audio_url"), str) else ""
            recording_id = recording_id_from_audio_url(audio_url) if audio_url else None
            pending = await ledger.repo.submitted_without_job_for_audio_url(audio_url) if audio_url else None
            if not should_import_untracked(
                created=created,
                watermark=watermark,
                recording_id=recording_id,
                pending_match=pending is not None,
                estimate_at=estimates.get(recording_id) if recording_id is not None else None,
            ):
                await _remember_covered_transcript(session, ledger, job_id, recording_id, created)
                continue
            try:
                full = await source.fetch_transcript(job_id)
            except Exception as exc:
                logger.warning(f"AssemblyAI import fetch failed | job={job_id} | error={exc}")
                continue
            if not isinstance(full, dict):
                continue
            await _record_untracked(session, ledger, job_id, audio_url, full, created or datetime.now(UTC))
            imported += 1
        page_details = payload.get("page_details")
        prev = page_details.get("prev_url") if isinstance(page_details, dict) else None
        if not isinstance(prev, str) or not prev:
            reached_end = True
            break
        page_url = prev
        resume_from = prev
    if save_cursor and reached_end and not list_failed:
        await _save_import_cursor(session, ledger, None)
    elif save_cursor and resume_from:
        await _save_import_cursor(session, ledger, resume_from)
    elif not save_cursor and not reached_end and not list_failed:
        logger.error("AssemblyAI import head hit the page cap while an older cursor is still pending")
    return imported


async def _import_cursor(ledger: ResourceLedgerService) -> str | None:
    row = await ledger.repo.get_by_idempotency(IMPORT_CURSOR_KEY)
    if row is None:
        return None
    details = row.details if isinstance(row.details, dict) else {}
    prev = details.get("prev_url")
    return prev if isinstance(prev, str) and prev else None


async def _save_import_cursor(session: AsyncSession, ledger: ResourceLedgerService, prev_url: str | None) -> None:
    row = await ledger.repo.get_by_idempotency(IMPORT_CURSOR_KEY)
    details: dict[str, Any] = {"prev_url": prev_url} if prev_url else {"done": True}
    now = datetime.now(UTC)
    if row is None:
        ledger.repo.add(
            ResourceLedgerModel(
                user_id="system",
                recording_id=None,
                provider="assemblyai",
                operation="import_cursor",
                status="completed",
                occurred_at=now,
                idempotency_key=IMPORT_CURSOR_KEY,
                details=details,
                created_at=now,
            )
        )
    else:
        row.details = details
        row.occurred_at = now
    await session.flush()


async def _remember_covered_transcript(
    session: AsyncSession,
    ledger: ResourceLedgerService,
    job_id: str,
    recording_id: int | None,
    created: datetime | None,
) -> None:
    """Remember an id whose minutes already sit in a segment_end estimate.

    ``audio_seconds`` stays null, so the minutes query does not add them again.
    The id is then known and a later pass does not walk the same history forever.
    """
    now = created or datetime.now(UTC)
    ledger.repo.add(
        ResourceLedgerModel(
            user_id="system",
            recording_id=recording_id,
            provider="assemblyai",
            operation="transcribe",
            provider_job_id=job_id,
            status="completed",
            audio_seconds=None,
            occurred_at=now,
            idempotency_key=f"aai:{job_id}",
            details={"basis": "already_estimated"},
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def _record_untracked(
    session: AsyncSession,
    ledger: ResourceLedgerService,
    job_id: str,
    audio_url: str,
    full: dict[str, Any],
    created: datetime,
) -> None:
    status = full.get("status")
    raw_seconds = full.get("audio_duration")
    try:
        seconds = float(raw_seconds) if raw_seconds is not None else None
    except (TypeError, ValueError):
        seconds = None
    model = full.get("speech_model_used") if isinstance(full.get("speech_model_used"), str) else None
    user_id, recording_id = await _attribute_transcript(session, audio_url)
    pending = await ledger.repo.submitted_without_job_for_audio_url(audio_url) if audio_url else None
    if pending is not None:
        pending.provider_job_id = job_id
        await session.flush()
        owner = pending.user_id if isinstance(pending.user_id, str) else user_id
        rec_id = pending.recording_id if isinstance(pending.recording_id, int) else recording_id
    else:
        owner, rec_id = user_id, recording_id
    if status == "completed" and seconds is not None:
        await ledger.mark_transcription_completed(
            user_id=owner,
            recording_id=rec_id,
            provider_job_id=job_id,
            audio_seconds=seconds,
            model=model,
            occurred_at=created,
        )
        return
    if status == "error":
        await ledger.mark_transcription_submitted(
            user_id=owner,
            recording_id=rec_id,
            provider_job_id=job_id,
            model=model,
            language=None,
            speech_models=None,
        )
        await ledger.mark_transcription_failed(provider_job_id=job_id)
        return
    if status in ("queued", "processing"):
        await ledger.mark_transcription_submitted(
            user_id=owner,
            recording_id=rec_id,
            provider_job_id=job_id,
            model=model,
            language=None,
            speech_models=None,
        )


def _token(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key) or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _version_time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    return datetime.now(UTC)
