"""Celery tasks for automation jobs."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.helpers.automation_window import (
    MATCH_QUERY_LIMIT,
    UNBOUNDED_MATCH_QUERY_LIMIT,
    resolve_job_timezone,
    resolve_job_window,
)
from api.helpers.schedule_converter import get_next_run_time, schedule_to_cron
from api.repositories.automation_repos import AutomationJobRepository, AutomationJobRunRepository
from api.repositories.template_repos import InputSourceRepository, RecordingTemplateRepository
from api.schemas.automation.filters import sanitize_automation_status_filter
from api.tasks.base import AutomationTask
from api.tasks.processing import run_recording_task
from config.settings import get_settings
from database.models import RecordingModel
from logger import get_logger
from models.recording import ProcessingStatus, SourceType

logger = get_logger()
settings = get_settings()

_WAIT_STATUSES = (ProcessingStatus.PENDING_SOURCE, ProcessingStatus.PENDING_CONVERSION)
_RUN_STATUS_BY_RESULT = {"success": "SUCCESS", "error": "FAILED", "skipped": "SKIPPED"}


def _resolve_status_filter(filters: dict) -> list[str] | None:
    """None means every status. Missing or invalid values use the MTS-aware default."""
    if "status" not in filters:
        return sanitize_automation_status_filter(None)
    return sanitize_automation_status_filter(filters.get("status"))


def _is_mts_link(recording: RecordingModel) -> bool:
    source = recording.source
    return source is not None and source.source_type == SourceType.MTS_LINK


def _should_enqueue_recording(recording: RecordingModel) -> bool:
    """Skip in-flight pipelines, expired rows, and Zoom-style PENDING_SOURCE."""
    if recording.on_air or recording.on_pause or recording.deleted:
        return False
    if recording.status == ProcessingStatus.EXPIRED:
        return False
    if recording.status != ProcessingStatus.PENDING_SOURCE:
        return True
    return _is_mts_link(recording)


def _order_templates(templates: list, template_ids: list[int]) -> list:
    """First-match order is the job checklist, not created_at."""
    by_id = {t.id: t for t in templates}
    return [by_id[tid] for tid in template_ids if tid in by_id]


def _sync_days(sync_config: dict | None) -> int | None:
    raw = (sync_config or {}).get("sync_days", 2)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 2


def _max_recordings(sync_config: dict | None) -> int | None:
    raw = (sync_config or {}).get("max_recordings")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _sync_on_run(sync_config: dict | None) -> bool:
    raw = (sync_config or {}).get("sync_on_run", True)
    return raw is not False


def _apply_enqueue_cap(
    matches: list[tuple[Any, Any]],
    max_recordings: int | None,
) -> list[tuple[Any, Any]]:
    """Wait-status pings always run; cap only full pipelines, newest first."""
    if max_recordings is None:
        return matches
    wait: list[tuple[Any, Any]] = []
    rest: list[tuple[Any, Any]] = []
    for recording, template in matches:
        if recording.status in _WAIT_STATUSES:
            wait.append((recording, template))
        else:
            rest.append((recording, template))
    rest.sort(key=lambda pair: recording_start(pair[0]), reverse=True)
    return wait + rest[:max_recordings]


def recording_start(recording: Any) -> datetime:
    start = getattr(recording, "start_time", None)
    if start is None:
        return datetime.min.replace(tzinfo=UTC)
    if start.tzinfo is None:
        return start.replace(tzinfo=UTC)
    return start


def _recordings_for_job_query(
    *,
    user_id: str,
    from_datetime: datetime | None,
    to_datetime: datetime,
    status_filter: list[str] | None,
    exclude_blank: bool,
    unbounded: bool,
):
    """Active recordings in the window. Wait statuses first so MTS pings are not starved."""
    query = (
        select(RecordingModel)
        .options(selectinload(RecordingModel.source))
        .where(
            RecordingModel.user_id == user_id,
            RecordingModel.deleted == False,  # noqa: E712
            RecordingModel.start_time <= to_datetime,
        )
    )
    if from_datetime is not None:
        query = query.where(RecordingModel.start_time >= from_datetime)
    if status_filter:
        query = query.where(RecordingModel.status.in_(status_filter))
    if exclude_blank:
        query = query.where(~RecordingModel.blank_record)
    limit = UNBOUNDED_MATCH_QUERY_LIMIT if unbounded else MATCH_QUERY_LIMIT
    return query.order_by(
        case((RecordingModel.status.in_(_WAIT_STATUSES), 0), else_=1),
        RecordingModel.start_time.asc(),
    ).limit(limit)


def _would_process_items(matches: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    """Snapshot of recordings that would start (or did start) a pipeline."""
    return [
        {
            "id": recording.id,
            "name": recording.display_name or "",
            "template_id": template.id,
            "template_name": template.name,
        }
        for recording, template in matches
    ]


@dataclass
class _MatchPlan:
    """Sync + match result. Callers bind/enqueue; preview only serializes this."""

    templates: list
    sources_to_sync: list
    synced_count: int
    recordings_found: int
    unmatched_count: int
    matches: list[tuple[Any, Any]]
    unmatched: list[Any]

    def preview_payload(self, job_id: int, user_id: str) -> dict[str, Any]:
        return {
            "status": "success",
            "job_id": job_id,
            "user_id": user_id,
            "synced_count": self.synced_count,
            "sources_synced": [s.id for s in self.sources_to_sync],
            "recordings_found": self.recordings_found,
            "matched_count": len(self.matches),
            "unmatched_count": self.unmatched_count,
            "would_process": _would_process_items(self.matches),
        }


async def _load_job_templates(session, job, user_id: str):
    template_repo = RecordingTemplateRepository(session)
    templates = await template_repo.find_by_ids(job.template_ids, user_id)
    templates = [t for t in templates if t.is_active and not t.is_draft]
    templates = _order_templates(templates, list(job.template_ids or []))
    return template_repo, templates


async def _sources_for_templates(session, templates, user_id: str):
    source_ids_set: set[int] = set()
    has_empty_source_ids = False
    for template in templates:
        if not template.matching_rules:
            has_empty_source_ids = True
            continue
        template_sources = template.matching_rules.get("source_ids")
        if template_sources is None or (isinstance(template_sources, list) and len(template_sources) == 0):
            has_empty_source_ids = True
        else:
            source_ids_set.update(template_sources)

    source_repo = InputSourceRepository(session)
    if has_empty_source_ids:
        all_sources = await source_repo.find_active_by_user(user_id)
        return [s for s in all_sources if s.credential_id]
    sources_to_sync = []
    for source_id in source_ids_set:
        source = await source_repo.find_by_id(source_id, user_id)
        if source and source.is_active and source.credential_id:
            sources_to_sync.append(source)
    return sources_to_sync


async def _sync_sources(session, job_id: int, user_id: str, sources_to_sync, from_date: str, to_date: str) -> int:
    from api.routers.input_sources import _sync_single_source

    synced_count = 0
    for source in sources_to_sync:
        try:
            result = await _sync_single_source(
                source_id=source.id,
                from_date=from_date,
                to_date=to_date,
                session=session,
                user_id=user_id,
            )
            if result["status"] == "success":
                synced_count += result["recordings_saved"]
                logger.info(
                    f"Job {job_id}: Synced source {source.id} - "
                    f"found={result['recordings_found']}, "
                    f"saved={result['recordings_saved']}, "
                    f"updated={result['recordings_updated']}"
                )
            else:
                logger.error(f"Job {job_id}: Failed to sync source {source.id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"Job {job_id}: Failed to sync source {source.id}: {e}")
            continue
    logger.info(f"Job {job_id}: Total synced {synced_count} new recordings")
    return synced_count


async def _sync_and_match(session, job, user_id: str, *, sync: bool) -> _MatchPlan | dict[str, Any]:
    """Sync sources (optional) and match recordings. Does not bind, enqueue, mark_run, or commit."""
    from api.routers.input_sources import _find_matching_template

    job_id = job.id
    _, templates = await _load_job_templates(session, job, user_id)
    if not templates:
        logger.warning(f"Job {job_id}: No active templates found")
        return {"status": "error", "job_id": job_id, "user_id": user_id, "error": "No active templates"}

    logger.info(f"Job {job_id}: Using {len(templates)} templates: {[t.id for t in templates]}")

    sources_to_sync = await _sources_for_templates(session, templates, user_id)
    if not sources_to_sync:
        logger.warning(f"Job {job_id}: No sources to sync")
        return {"status": "error", "job_id": job_id, "user_id": user_id, "error": "No sources to sync"}

    tz_name = resolve_job_timezone(job.schedule)
    days = _sync_days(job.sync_config)
    match_window = resolve_job_window(days, tz_name=tz_name, for_api_sync=False)
    synced_count = 0
    if sync:
        api_window = resolve_job_window(days, tz_name=tz_name, for_api_sync=True)
        synced_count = await _sync_sources(
            session,
            job_id,
            user_id,
            sources_to_sync,
            api_window.from_date or api_window.to_date,
            api_window.to_date,
        )

    filters = job.filters or {}
    status_filter = _resolve_status_filter(filters)
    exclude_blank = filters.get("exclude_blank", True)
    if exclude_blank is None:
        exclude_blank = True
    query = _recordings_for_job_query(
        user_id=user_id,
        from_datetime=match_window.from_datetime,
        to_datetime=match_window.to_datetime,
        status_filter=status_filter,
        exclude_blank=bool(exclude_blank),
        unbounded=match_window.from_datetime is None,
    )
    result = await session.execute(query)
    recordings_to_process = list(result.scalars().all())
    logger.info(
        f"Job {job_id}: Found {len(recordings_to_process)} recordings to process "
        f"(status={status_filter}, exclude_blank={exclude_blank}, "
        f"date_range={match_window.from_datetime} to {match_window.to_datetime.isoformat()}, sync={sync})"
    )

    matches: list[tuple[Any, Any]] = []
    unmatched: list[Any] = []
    for recording in recordings_to_process:
        if not _should_enqueue_recording(recording):
            continue
        matched_template = _find_matching_template(
            display_name=recording.display_name,
            source_id=recording.input_source_id or 0,
            templates=templates,
        )
        if matched_template:
            matches.append((recording, matched_template))
        else:
            unmatched.append(recording)

    matches = _apply_enqueue_cap(matches, _max_recordings(job.sync_config))

    return _MatchPlan(
        templates=templates,
        sources_to_sync=sources_to_sync,
        synced_count=synced_count,
        recordings_found=len(recordings_to_process),
        unmatched_count=len(unmatched),
        matches=matches,
        unmatched=unmatched,
    )


async def _preview_job(session, job, user_id: str, *, sync: bool) -> dict[str, Any]:
    """Optional sync + match, then commit so catalog rows from sync survive. No bind/enqueue."""
    plan = await _sync_and_match(session, job, user_id, sync=sync)
    if isinstance(plan, dict):
        return plan
    payload = plan.preview_payload(job.id, user_id)
    await session.commit()
    return payload


async def _record_run(session, job_id: int, user_id: str, started_at, result: dict, trigger: str) -> None:
    """Persist a finished execution when no RUNNING row was opened (skipped before start)."""
    finished_at = datetime.now(UTC)
    try:
        await AutomationJobRunRepository(session).create(
            job_id=job_id,
            user_id=user_id,
            status=_RUN_STATUS_BY_RESULT.get(result.get("status", ""), "FAILED"),
            trigger=trigger,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=int((finished_at - started_at).total_seconds()),
            synced_count=result.get("synced_count", 0) or 0,
            recordings_found=result.get("recordings_found", 0) or 0,
            matched_count=result.get("matched_count", 0) or 0,
            processed_count=result.get("processed_count", 0) or 0,
            error=result.get("error") or result.get("reason"),
            affected_recordings=result.get("would_process"),
        )
    except Exception as exc:  # pragma: no cover - history must not mask results
        logger.error(f"Failed to record run for job {job_id}: {exc}")


async def _finish_run(session, run, started_at, result: dict) -> None:
    finished_at = datetime.now(UTC)
    try:
        await AutomationJobRunRepository(session).finish(
            run,
            status=_RUN_STATUS_BY_RESULT.get(result.get("status", ""), "FAILED"),
            finished_at=finished_at,
            duration_seconds=int((finished_at - started_at).total_seconds()),
            synced_count=result.get("synced_count", 0) or 0,
            recordings_found=result.get("recordings_found", 0) or 0,
            matched_count=result.get("matched_count", 0) or 0,
            processed_count=result.get("processed_count", 0) or 0,
            error=result.get("error") or result.get("reason"),
            affected_recordings=result.get("would_process"),
        )
    except Exception as exc:  # pragma: no cover
        logger.error(f"Failed to finish run {getattr(run, 'id', None)}: {exc}")


async def _execute_job(session, job_id: int, user_id: str, *, sync: bool) -> dict[str, Any]:
    job_repo = AutomationJobRepository(session)
    job = await job_repo.get_by_id(job_id, user_id)

    if not job or not job.is_active:
        logger.warning(f"Job {job_id} not found or inactive")
        return {"status": "skipped", "reason": "Job not found or inactive", "user_id": user_id}

    try:
        logger.info(f"Starting automation job {job_id} ({job.name})")
        plan = await _sync_and_match(session, job, user_id, sync=sync)
        if isinstance(plan, dict):
            return plan

        template_repo = RecordingTemplateRepository(session)
        for recording, matched_template in plan.matches:
            newly_bound = (not recording.is_mapped) or recording.template_id != matched_template.id
            if newly_bound:
                recording.template_id = matched_template.id
                recording.is_mapped = True
                await template_repo.increment_usage(matched_template)

        await session.commit()

        processed_recordings = []
        for recording, matched_template in plan.matches:
            task = run_recording_task.delay(
                recording_id=recording.id,
                user_id=user_id,
                manual_override=job.processing_config,
            )
            processed_recordings.append(
                {
                    "recording_id": recording.id,
                    "template_id": matched_template.id,
                    "task_id": str(task.id),
                }
            )
            logger.debug(
                f"Job {job_id}: Recording {recording.id} matched template {matched_template.id}, task={task.id}"
            )

        logger.info(
            f"Job {job_id}: Matched {len(plan.matches)} recordings, unmatched {plan.unmatched_count}, "
            f"started {len(processed_recordings)} pipelines"
        )

        cron_expr, _ = schedule_to_cron(job.schedule)
        timezone = resolve_job_timezone(job.schedule)
        next_run = get_next_run_time(cron_expr, timezone)
        await job_repo.mark_run(job, next_run)

        payload = plan.preview_payload(job_id, user_id)
        payload["processed_count"] = len(processed_recordings)
        payload["processed_recordings"] = processed_recordings
        payload["next_run_at"] = next_run.isoformat()
        return payload

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        return {"status": "error", "job_id": job_id, "user_id": user_id, "error": str(e)}


@celery_app.task(
    bind=True,
    base=AutomationTask,
    name="automation.run_job",
    max_retries=settings.celery.automation_max_retries,
    default_retry_delay=settings.celery.automation_retry_delay,
)
def run_automation_job_task(self, job_id: int, user_id: str, trigger: str = "SCHEDULE", sync: bool | None = None):
    """
    Execute automation job:
    1. Load templates in job.template_ids order
    2. Optionally sync recordings from required sources
    3. Filter recordings by automation filters
    4. Match recordings with templates
    5. Process matched recordings with config override
    """

    async def _run():
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            started_at = datetime.now(UTC)
            job_repo = AutomationJobRepository(session)
            job = await job_repo.get_by_id(job_id, user_id)
            if not job or not job.is_active:
                result = {"status": "skipped", "reason": "Job not found or inactive", "user_id": user_id}
                await _record_run(session, job_id, user_id, started_at, result, trigger)
                return result

            do_sync = _sync_on_run(job.sync_config) if sync is None else bool(sync)
            run_repo = AutomationJobRunRepository(session)
            try:
                run = await run_repo.create_running(
                    job_id=job_id,
                    user_id=user_id,
                    trigger=trigger,
                    started_at=started_at,
                )
            except IntegrityError:
                await session.rollback()
                return {"status": "skipped", "reason": "Job already running", "user_id": user_id}

            result = await _execute_job(session, job_id, user_id, sync=do_sync)
            await _finish_run(session, run, started_at, result)
            return result

    return self.run_async(_run())


@celery_app.task(
    bind=True,
    base=AutomationTask,
    name="automation.dry_run",
    max_retries=settings.celery.automation_max_retries,
    default_retry_delay=settings.celery.automation_retry_delay,
)
def dry_run_automation_job_task(self, job_id: int, user_id: str, sync: bool = False):
    """Match recordings without binding or starting pipelines. Sync only if requested."""

    self.update_progress(user_id, 5, "Refreshing sources…" if sync else "Matching recordings…")

    async def _run():
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            job_repo = AutomationJobRepository(session)
            job = await job_repo.get_by_id(job_id, user_id)
            if not job:
                return {"status": "error", "error": "Job not found", "user_id": user_id}
            try:
                return await _preview_job(session, job, user_id, sync=sync)
            except Exception as e:
                logger.error(f"Dry run failed for job {job_id}: {e}")
                return {"status": "error", "error": str(e), "user_id": user_id}

    return self.run_async(_run())
