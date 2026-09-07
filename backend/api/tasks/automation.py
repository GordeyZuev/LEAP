"""Celery tasks for automation jobs."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import selectinload

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
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


def _resolve_status_filter(filters: dict) -> list[str] | None:
    """None means every status. Missing or invalid values use the MTS-aware default."""
    if "status" not in filters:
        return sanitize_automation_status_filter(None)
    return sanitize_automation_status_filter(filters.get("status"))


_WAIT_STATUSES = frozenset(
    {
        ProcessingStatus.PENDING_SOURCE,
        ProcessingStatus.PENDING_CONVERSION,
        ProcessingStatus.DOWNLOADING,
        ProcessingStatus.PROCESSING,
        ProcessingStatus.UPLOADING,
    }
)


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


def _recordings_for_job_query(
    *,
    user_id: str,
    from_datetime: datetime,
    to_datetime: datetime,
    status_filter: list[str] | None,
    exclude_blank: bool,
):
    """Active recordings in the sync window. Wait statuses are first so MTS pings are not starved by limit(1000)."""
    query = (
        select(RecordingModel)
        .options(selectinload(RecordingModel.source))
        .where(
            RecordingModel.user_id == user_id,
            RecordingModel.deleted == False,  # noqa: E712
            RecordingModel.start_time >= from_datetime,
            RecordingModel.start_time <= to_datetime,
        )
    )
    if status_filter:
        query = query.where(RecordingModel.status.in_(status_filter))
    if exclude_blank:
        query = query.where(~RecordingModel.blank_record)
    wait = (ProcessingStatus.PENDING_SOURCE, ProcessingStatus.PENDING_CONVERSION)
    return query.order_by(
        case((RecordingModel.status.in_(wait), 0), else_=1),
        RecordingModel.start_time.asc(),
    ).limit(1000)


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


async def _sync_sources(session, job_id: int, user_id: str, sources_to_sync, days: int) -> int:
    from api.routers.input_sources import _sync_single_source

    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
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


async def _sync_and_match(session, job, user_id: str) -> _MatchPlan | dict[str, Any]:
    """Sync sources and match recordings. Does not bind, skip unmatched, enqueue, mark_run, or commit."""
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

    days = (job.sync_config or {}).get("sync_days", 2)
    synced_count = await _sync_sources(session, job_id, user_id, sources_to_sync, days)

    filters = job.filters or {}
    status_filter = _resolve_status_filter(filters)
    exclude_blank = filters.get("exclude_blank", True)
    from_datetime = datetime.now(UTC) - timedelta(days=days)
    to_datetime = datetime.now(UTC)
    query = _recordings_for_job_query(
        user_id=user_id,
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        status_filter=status_filter,
        exclude_blank=exclude_blank,
    )
    result = await session.execute(query)
    recordings_to_process = list(result.scalars().all())
    logger.info(
        f"Job {job_id}: Found {len(recordings_to_process)} recordings to process "
        f"(status={status_filter}, exclude_blank={exclude_blank}, "
        f"date_range={from_datetime.isoformat()} to {to_datetime.isoformat()})"
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

    return _MatchPlan(
        templates=templates,
        sources_to_sync=sources_to_sync,
        synced_count=synced_count,
        recordings_found=len(recordings_to_process),
        unmatched_count=len(unmatched),
        matches=matches,
        unmatched=unmatched,
    )


async def _preview_job(session, job, user_id: str) -> dict[str, Any]:
    """Sync + match, then commit so catalog rows from sync survive. No bind/enqueue."""
    plan = await _sync_and_match(session, job, user_id)
    if isinstance(plan, dict):
        return plan
    payload = plan.preview_payload(job.id, user_id)
    # Snapshot first: commit expires ORM instances. _sync_single_source does not
    # commit; without this, preview lists rows that roll back when the session closes.
    await session.commit()
    return payload


# Maps the task's result payload onto a history row. Kept next to the task so
# the two stay in step when the payload changes.
_RUN_STATUS_BY_RESULT = {"success": "SUCCESS", "error": "FAILED", "skipped": "SKIPPED"}


async def _record_run(session, job_id: int, user_id: str, started_at, result: dict, trigger: str) -> None:
    """Persist one execution. Never lets bookkeeping break the run itself."""
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


async def _execute_job(session, job_id: int, user_id: str) -> dict[str, Any]:
    job_repo = AutomationJobRepository(session)
    job = await job_repo.get_by_id(job_id, user_id)

    if not job or not job.is_active:
        logger.warning(f"Job {job_id} not found or inactive")
        return {"status": "skipped", "reason": "Job not found or inactive", "user_id": user_id}

    try:
        logger.info(f"Starting automation job {job_id} ({job.name})")
        plan = await _sync_and_match(session, job, user_id)
        if isinstance(plan, dict):
            return plan

        template_repo = RecordingTemplateRepository(session)
        for recording, matched_template in plan.matches:
            newly_bound = (not recording.is_mapped) or recording.template_id != matched_template.id
            if newly_bound:
                recording.template_id = matched_template.id
                recording.is_mapped = True
                await template_repo.increment_usage(matched_template)

                from api.services.playlist_service import add_from_bound_template

                await add_from_bound_template(session, user_id, recording)

        for recording in plan.unmatched:
            if recording.status not in _WAIT_STATUSES:
                recording.status = ProcessingStatus.SKIPPED
                recording.failed_reason = "No matching template"
            logger.debug(
                f"Job {job_id}: Recording {recording.id} has no matching template"
                + (" - left in wait status" if recording.status in _WAIT_STATUSES else " - SKIPPED")
            )

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
        timezone = job.schedule.get("timezone", "Europe/Moscow")
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
def run_automation_job_task(self, job_id: int, user_id: str, trigger: str = "SCHEDULE"):
    """
    Execute automation job:
    1. Load templates and collect source_ids
    2. Sync recordings from all required sources
    3. Filter recordings by automation filters
    4. Match recordings with templates
    5. Process matched recordings with config override
    """

    async def _run():
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            started_at = datetime.now(UTC)
            result = await _execute_job(session, job_id, user_id)
            await _record_run(session, job_id, user_id, started_at, result, trigger)
            return result

    return self.run_async(_run())


@celery_app.task(
    bind=True,
    base=AutomationTask,
    name="automation.dry_run",
    max_retries=settings.celery.automation_max_retries,
    default_retry_delay=settings.celery.automation_retry_delay,
)
def dry_run_automation_job_task(self, job_id: int, user_id: str):
    """Sync sources and match recordings without binding, skipping, or starting pipelines."""

    self.update_progress(user_id, 5, "Syncing sources…")

    async def _run():
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            job_repo = AutomationJobRepository(session)
            job = await job_repo.get_by_id(job_id, user_id)
            if not job:
                return {"status": "error", "error": "Job not found", "user_id": user_id}
            try:
                return await _preview_job(session, job, user_id)
            except Exception as e:
                logger.error(f"Dry run failed for job {job_id}: {e}")
                return {"status": "error", "error": str(e), "user_id": user_id}

    return self.run_async(_run())
