"""Celery tasks for syncing sources with multi-tenancy support."""

from api.celery_app import celery_app
from api.dependencies import get_async_session_maker
from api.repositories.template_repos import InputSourceRepository
from api.tasks.base import SyncTask
from config.settings import get_settings
from logger import format_details, get_logger, short_task_id, short_user_id

logger = get_logger()
settings = get_settings()


@celery_app.task(
    bind=True,
    base=SyncTask,
    name="api.tasks.sync.sync_single_source",
    max_retries=settings.celery.sync_max_retries,
    default_retry_delay=settings.celery.sync_retry_delay,
)
def sync_single_source_task(
    self,
    source_id: int,
    user_id: str,
    from_date: str = "2025-01-01",
    to_date: str | None = None,
) -> dict:
    """
    Syncing one source (Celery task).

    Args:
        source_id: ID of source
        user_id: ID of user
        from_date: Start date in format YYYY-MM-DD
        to_date: End date in format YYYY-MM-DD (optional)

    Returns:
        Result of syncing
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info(f"Syncing source | {format_details(source=source_id)}")

            self.update_progress(user_id, 10, f"Syncing source {source_id}...", step="sync")

            # Use run_async for proper event loop isolation
            result = self.run_async(_async_sync_single_source(self, source_id, user_id, from_date, to_date))
            return self.build_result(user_id=user_id, **result)

        except Exception as e:
            logger.error(f"Sync task failed | {format_details(source=source_id, error=e)}", exc_info=True)
            raise


@celery_app.task(
    bind=True,
    base=SyncTask,
    name="api.tasks.sync.batch_sync_sources",
    max_retries=settings.celery.sync_max_retries,
    default_retry_delay=settings.celery.sync_retry_delay,
)
def bulk_sync_sources_task(
    self,
    source_ids: list[int],
    user_id: str,
    from_date: str = "2025-01-01",
    to_date: str | None = None,
) -> dict:
    """
    Batch syncing multiple sources (Celery task).

    Args:
        source_ids: List of source IDs
        user_id: ID of user
        from_date: Start date in format YYYY-MM-DD
        to_date: End date in format YYYY-MM-DD (optional)

    Returns:
        Results of syncing all sources
    """
    with logger.contextualize(
        task_id=short_task_id(self.request.id),
        user_id=short_user_id(user_id),
    ):
        try:
            logger.info(f"Batch syncing | {format_details(sources=len(source_ids))}")

            self.update_progress(
                user_id,
                5,
                f"Starting batch sync of {len(source_ids)} sources...",
                step="batch_sync",
            )

            # Use run_async for proper event loop isolation
            result = self.run_async(_async_batch_sync_sources(self, source_ids, user_id, from_date, to_date))
            return self.build_result(user_id=user_id, **result)

        except Exception as e:
            logger.error(f"Batch sync failed | {format_details(sources=source_ids, error=e)}", exc_info=True)
            raise


async def _async_sync_single_source(
    task,
    source_id: int,
    user_id: str,
    from_date: str,
    to_date: str | None,
) -> dict:
    """Async wrapper for syncing one source."""
    session_maker = get_async_session_maker()

    async with session_maker() as session:
        task.update_progress(user_id, 20, f"Loading source {source_id}...", step="sync")

        # Import here to avoid circular imports
        from api.routers.input_sources import _sync_single_source

        result = await _sync_single_source(source_id, from_date, to_date, session, user_id)

        if result["status"] == "success":
            await session.commit()

            task.update_progress(user_id, 90, "Sync completed", step="sync")

            # Get source for additional information
            repo = InputSourceRepository(session)
            source = await repo.find_by_id(source_id, user_id)

            return {
                "status": "success",
                "source_id": source_id,
                "source_name": source.name if source else None,
                "source_type": source.source_type if source else "UNKNOWN",
                "recordings_found": result.get("recordings_found", 0),
                "recordings_saved": result.get("recordings_saved", 0),
                "recordings_updated": result.get("recordings_updated", 0),
            }
        return {
            "status": "error",
            "source_id": source_id,
            "error": result.get("error", "Unknown error"),
        }


async def _async_batch_sync_sources(
    task,
    source_ids: list[int],
    user_id: str,
    from_date: str,
    to_date: str | None,
) -> dict:
    """Async wrapper for batch syncing sources."""
    session_maker = get_async_session_maker()
    results = []
    successful = 0
    failed = 0

    async with session_maker() as session:
        repo = InputSourceRepository(session)

        for idx, source_id in enumerate(source_ids):
            progress = 10 + int((idx / len(source_ids)) * 80)
            task.update_progress(
                user_id,
                progress,
                f"Syncing source {idx + 1}/{len(source_ids)}...",
                step="batch_sync",
                current_source=source_id,
            )

            # Get source for name
            source = await repo.find_by_id(source_id, user_id)
            source_name = source.name if source else None

            try:
                # Import here to avoid circular imports
                from api.routers.input_sources import _sync_single_source

                result = await _sync_single_source(source_id, from_date, to_date, session, user_id)

                if result["status"] == "success":
                    successful += 1
                    results.append(
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "status": "success",
                            "recordings_found": result.get("recordings_found"),
                            "recordings_saved": result.get("recordings_saved"),
                            "recordings_updated": result.get("recordings_updated"),
                        }
                    )
                else:
                    failed += 1
                    results.append(
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "status": "error",
                            "error": result.get("error", "Unknown error"),
                        }
                    )

            except Exception as e:
                logger.error(f"Unexpected sync error | {format_details(source=source_id, error=e)}", exc_info=True)
                failed += 1
                results.append(
                    {
                        "source_id": source_id,
                        "source_name": source_name,
                        "status": "error",
                        "error": str(e),
                    }
                )

        await session.commit()

        return {
            "status": "success",
            "message": f"Batch sync completed: {successful} successful, {failed} failed",
            "total_sources": len(source_ids),
            "successful": successful,
            "failed": failed,
            "results": results,
        }
