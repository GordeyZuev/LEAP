"""Automation job management endpoints"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.core.dependencies import get_service_context
from api.helpers.beat_sync import remove_job_from_beat, sync_job_to_beat
from api.repositories.automation_repos import AutomationJobRepository
from api.schemas.automation import (
    AutomationJobCreate,
    AutomationJobResponse,
    AutomationJobUpdate,
    JobListResponse,
    TriggerJobResponse,
)
from api.schemas.common.pagination import paginate_list
from api.services.automation_service import AutomationService
from api.tasks.automation import dry_run_automation_job_task, run_automation_job_task

router = APIRouter(prefix="/api/v1/automation/jobs", tags=["Automation"])

JOB_SORT_FIELDS = {"created_at", "updated_at", "name", "next_run_at"}


@router.get("", response_model=JobListResponse)
async def list_jobs(
    active_only: bool = Query(False, description="Filter only active jobs"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    ctx=Depends(get_service_context),
):
    """List user's automation jobs with pagination."""
    repo = AutomationJobRepository(ctx.session)
    jobs = await repo.get_user_jobs(ctx.user_id, active_only)

    items, total, total_pages = paginate_list(jobs, page, per_page, sort_by, sort_order, JOB_SORT_FIELDS)

    return JobListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.post("", response_model=AutomationJobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    data: AutomationJobCreate,
    ctx=Depends(get_service_context),
):
    """Create new automation job."""
    service = AutomationService(ctx.session, ctx.user_id)
    job = await service.create_job(data.model_dump())

    await sync_job_to_beat(ctx.session, job)

    return job


@router.get("/{job_id}", response_model=AutomationJobResponse)
async def get_job(
    job_id: int,
    ctx=Depends(get_service_context),
):
    """Get automation job details."""
    repo = AutomationJobRepository(ctx.session)
    job = await repo.get_by_id(job_id, ctx.user_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found")
    return job


@router.patch("/{job_id}", response_model=AutomationJobResponse)
async def update_job(
    job_id: int,
    data: AutomationJobUpdate,
    ctx=Depends(get_service_context),
):
    """Update automation job."""
    service = AutomationService(ctx.session, ctx.user_id)

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    job = await service.update_job(job_id, updates)

    await sync_job_to_beat(ctx.session, job)

    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: int,
    ctx=Depends(get_service_context),
):
    """Delete automation job."""
    repo = AutomationJobRepository(ctx.session)
    job = await repo.get_by_id(job_id, ctx.user_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found")

    await remove_job_from_beat(ctx.session, job_id)
    await repo.delete(job)


@router.post("/{job_id}/run", response_model=TriggerJobResponse)
async def trigger_job(
    job_id: int,
    dry_run: bool = Query(False, description="Preview mode without execution"),
    ctx=Depends(get_service_context),
) -> TriggerJobResponse:
    """
    Manually trigger automation job.
    Use dry_run=true to preview what will happen without executing.
    """
    repo = AutomationJobRepository(ctx.session)
    job = await repo.get_by_id(job_id, ctx.user_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found")

    if dry_run:
        task = dry_run_automation_job_task.delay(job_id, ctx.user_id)
        return TriggerJobResponse(
            task_id=str(task.id),
            mode="dry_run",
            message="Preview mode - no changes will be made",
        )
    task = run_automation_job_task.delay(job_id, ctx.user_id)
    return TriggerJobResponse(
        task_id=str(task.id),
        mode="execute",
        message="Job execution started",
    )
