"""Celery tasks for automation jobs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.helpers.schedule_converter import get_next_run_time, schedule_to_cron
from api.repositories.automation_repos import AutomationJobRepository
from api.repositories.template_repos import InputSourceRepository, RecordingTemplateRepository
from api.tasks.base import AutomationTask
from api.tasks.processing import run_recording_task
from config.settings import get_settings
from database.models import RecordingModel
from logger import get_logger
from models.recording import ProcessingStatus

logger = get_logger()
settings = get_settings()


@celery_app.task(
    bind=True,
    base=AutomationTask,
    name="automation.run_job",
    max_retries=settings.celery.automation_max_retries,
    default_retry_delay=settings.celery.automation_retry_delay,
)
def run_automation_job_task(self, job_id: int, user_id: str):
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
            job_repo = AutomationJobRepository(session)
            job = await job_repo.get_by_id(job_id, user_id)

            if not job or not job.is_active:
                logger.warning(f"Job {job_id} not found or inactive")
                return {"status": "skipped", "reason": "Job not found or inactive"}

            try:
                logger.info(f"Starting automation job {job_id} ({job.name})")

                # Step 1: Load and validate templates
                template_repo = RecordingTemplateRepository(session)
                templates = await template_repo.find_by_ids(job.template_ids, user_id)
                templates = [t for t in templates if t.is_active and not t.is_draft]

                if not templates:
                    logger.warning(f"Job {job_id}: No active templates found")
                    return {"status": "error", "error": "No active templates"}

                logger.info(f"Job {job_id}: Using {len(templates)} templates: {[t.id for t in templates]}")

                # Step 2: Collect source_ids from templates
                source_ids_set = set()
                has_empty_source_ids = False

                for template in templates:
                    # If matching_rules is None or doesn't specify source_ids → match all sources
                    if not template.matching_rules:
                        has_empty_source_ids = True
                    else:
                        template_sources = template.matching_rules.get("source_ids")
                        if template_sources is None or (
                            isinstance(template_sources, list) and len(template_sources) == 0
                        ):
                            # No source_ids specified or empty list → match all sources
                            has_empty_source_ids = True
                        else:
                            # Specific source_ids → collect them
                            source_ids_set.update(template_sources)

                # Step 3: Determine sources to sync
                source_repo = InputSourceRepository(session)
                if has_empty_source_ids:
                    # If ANY template has no source_ids → sync ALL sources
                    all_sources = await source_repo.find_active_by_user(user_id)
                    sources_to_sync = [s for s in all_sources if s.credential_id]
                    logger.info(f"Job {job_id}: Syncing ALL sources ({len(sources_to_sync)} total)")
                else:
                    # Sync only specified sources
                    sources_to_sync = []
                    for source_id in source_ids_set:
                        source = await source_repo.find_by_id(source_id, user_id)
                        if source and source.is_active and source.credential_id:
                            sources_to_sync.append(source)
                    logger.info(f"Job {job_id}: Syncing sources: {list(source_ids_set)}")

                if not sources_to_sync:
                    logger.warning(f"Job {job_id}: No sources to sync")
                    return {"status": "error", "error": "No sources to sync"}

                # Step 4: Sync recordings from all sources using existing _sync_single_source
                sync_config = job.sync_config
                days = sync_config.get("sync_days", 2)
                to_date = datetime.now().strftime("%Y-%m-%d")
                from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

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

                # Step 5: Query recordings using filters
                filters = job.filters or {}
                status_filter = filters.get("status", ["INITIALIZED"])
                exclude_blank = filters.get("exclude_blank", True)

                # Calculate date range from sync_days
                # Use UTC to match timezone-aware start_time in DB
                from_datetime = datetime.now(UTC) - timedelta(days=days)
                to_datetime = datetime.now(UTC)

                query = select(RecordingModel).where(
                    RecordingModel.user_id == user_id,
                    RecordingModel.start_time >= from_datetime,
                    RecordingModel.start_time <= to_datetime,
                )

                # Apply status filter
                if status_filter:
                    query = query.where(RecordingModel.status.in_(status_filter))

                # Apply exclude_blank filter
                if exclude_blank:
                    query = query.where(~RecordingModel.blank_record)

                query = query.limit(1000)
                result = await session.execute(query)
                recordings_to_process = list(result.scalars().all())

                logger.info(
                    f"Job {job_id}: Found {len(recordings_to_process)} recordings to process "
                    f"(status={status_filter}, exclude_blank={exclude_blank}, "
                    f"date_range={from_datetime.isoformat()} to {to_datetime.isoformat()})"
                )

                # Step 6: Match and process recordings
                from api.routers.input_sources import _find_matching_template

                processed_recordings = []
                matched_count = 0
                unmatched_count = 0

                for recording in recordings_to_process:
                    # Find first matching template
                    matched_template = _find_matching_template(
                        display_name=recording.display_name,
                        source_id=recording.input_source_id or 0,
                        templates=templates,
                    )

                    if matched_template:
                        matched_count += 1
                        # Apply template to recording
                        recording.template_id = matched_template.id
                        recording.is_mapped = True

                        # Start run task with automation processing_config as manual_override
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
                    else:
                        unmatched_count += 1
                        # Mark as SKIPPED if no template matched
                        recording.status = ProcessingStatus.SKIPPED
                        recording.failed_reason = "No matching template"
                        logger.debug(f"Job {job_id}: Recording {recording.id} has no matching template - SKIPPED")

                await session.commit()

                logger.info(
                    f"Job {job_id}: Matched {matched_count} recordings, unmatched {unmatched_count}, "
                    f"started {len(processed_recordings)} pipelines"
                )

                # Step 7: Update job stats
                cron_expr, _ = schedule_to_cron(job.schedule)
                timezone = job.schedule.get("timezone", "Europe/Moscow")
                next_run = get_next_run_time(cron_expr, timezone)
                await job_repo.mark_run(job, next_run)

                return {
                    "status": "success",
                    "job_id": job_id,
                    "synced_count": synced_count,
                    "sources_synced": [s.id for s in sources_to_sync],
                    "recordings_found": len(recordings_to_process),
                    "matched_count": matched_count,
                    "unmatched_count": unmatched_count,
                    "processed_count": len(processed_recordings),
                    "processed_recordings": processed_recordings,
                    "next_run_at": next_run.isoformat(),
                }

            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}", exc_info=True)
                return {"status": "error", "job_id": job_id, "error": str(e)}

    return self.run_async(_run())


@celery_app.task(
    bind=True,
    base=AutomationTask,
    name="automation.dry_run",
    max_retries=settings.celery.automation_max_retries,
    default_retry_delay=settings.celery.automation_retry_delay,
)
def dry_run_automation_job_task(self, job_id: int, user_id: str):
    """
    Preview what the job would do without executing.
    Returns estimated counts without actually processing.
    """

    async def _run():
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            job_repo = AutomationJobRepository(session)
            job = await job_repo.get_by_id(job_id, user_id)

            if not job:
                return {"status": "error", "error": "Job not found"}

            try:
                # Load templates
                template_repo = RecordingTemplateRepository(session)
                templates = await template_repo.find_by_ids(job.template_ids, user_id)
                templates = [t for t in templates if t.is_active and not t.is_draft]

                if not templates:
                    return {"status": "error", "error": "No active templates"}

                # Collect source_ids
                source_ids_set = set()
                has_empty_source_ids = False
                for template in templates:
                    # If matching_rules is None or doesn't specify source_ids → match all sources
                    if not template.matching_rules:
                        has_empty_source_ids = True
                    else:
                        template_sources = template.matching_rules.get("source_ids")
                        if template_sources is None or (
                            isinstance(template_sources, list) and len(template_sources) == 0
                        ):
                            # No source_ids specified or empty list → match all sources
                            has_empty_source_ids = True
                        else:
                            # Specific source_ids → collect them
                            source_ids_set.update(template_sources)

                # Count sources to sync
                source_repo = InputSourceRepository(session)
                if has_empty_source_ids:
                    all_sources = await source_repo.find_active_by_user(user_id)
                    sources_count = len([s for s in all_sources if s.credential_id])
                else:
                    sources_count = len(source_ids_set)

                # Query recordings that match filters
                sync_config = job.sync_config
                days = sync_config.get("sync_days", 2)
                filters = job.filters or {}
                status_filter = filters.get("status", ["INITIALIZED"])
                exclude_blank = filters.get("exclude_blank", True)

                # Use UTC to match timezone-aware start_time in DB
                from_datetime = datetime.now(UTC) - timedelta(days=days)
                to_datetime = datetime.now(UTC)

                query = select(RecordingModel).where(
                    RecordingModel.user_id == user_id,
                    RecordingModel.start_time >= from_datetime,
                    RecordingModel.start_time <= to_datetime,
                )

                if status_filter:
                    query = query.where(RecordingModel.status.in_(status_filter))

                # Apply exclude_blank filter
                if exclude_blank:
                    query = query.where(~RecordingModel.blank_record)

                query = query.limit(1000)
                result = await session.execute(query)
                recordings = list(result.scalars().all())

                # Estimate matched count
                from api.routers.input_sources import _find_matching_template

                estimated_matched = 0
                for recording in recordings:
                    matched_template = _find_matching_template(
                        display_name=recording.display_name,
                        source_id=recording.input_source_id or 0,
                        templates=templates,
                    )
                    if matched_template:
                        estimated_matched += 1

                avg_duration_minutes = 15
                estimated_duration = estimated_matched * avg_duration_minutes

                return {
                    "status": "success",
                    "job_id": job_id,
                    "sources_to_sync": sources_count,
                    "sync_window_days": days,
                    "recordings_in_window": len(recordings),
                    "estimated_matched": estimated_matched,
                    "estimated_unmatched": len(recordings) - estimated_matched,
                    "estimated_duration_minutes": estimated_duration,
                    "templates_used": [t.id for t in templates],
                }

            except Exception as e:
                logger.error(f"Dry run failed for job {job_id}: {e}")
                return {"status": "error", "error": str(e)}

    return self.run_async(_run())
