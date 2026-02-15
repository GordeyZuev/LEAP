"""Automation job service"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.helpers.schedule_converter import get_next_run_time, schedule_to_cron, validate_min_interval
from api.repositories.automation_repos import AutomationJobRepository
from api.repositories.template_repos import RecordingTemplateRepository
from api.services.quota_service import QuotaService


class AutomationService:
    """Service for managing automation jobs with business logic."""

    def __init__(self, session: AsyncSession, user_id: str):
        self.session = session
        self.user_id = user_id
        self.job_repo = AutomationJobRepository(session)
        self.quota_service = QuotaService(session)
        self.template_repo = RecordingTemplateRepository(session)

    async def get_user_quotas(self) -> dict[str, int | None]:
        """Get user effective quotas."""
        return await self.quota_service.get_effective_quotas(self.user_id)

    async def validate_quota(self) -> dict[str, int | None]:
        """Validate that user hasn't exceeded automation job limit."""
        quotas = await self.get_user_quotas()
        max_jobs = quotas["max_automation_jobs"]

        # NULL = unlimited
        if max_jobs is None:
            return quotas

        current_count = await self.job_repo.count_user_jobs(self.user_id)

        if current_count >= max_jobs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Automation job limit reached ({max_jobs} jobs maximum)",
            )

        return quotas

    async def validate_schedule(self, schedule: dict, quotas: dict[str, int | None]) -> None:
        """Validate that schedule meets minimum interval requirement."""
        cron_expr, _ = schedule_to_cron(schedule)
        min_interval = quotas["min_automation_interval_hours"]

        # NULL = no minimum interval
        if min_interval is None:
            return

        if not validate_min_interval(cron_expr, min_interval):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Schedule interval must be at least {min_interval} hour(s)",
            )

    async def validate_templates(self, template_ids: list[int]) -> None:
        """Validate templates exist, are active, and not draft."""
        if not template_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="template_ids cannot be empty")

        templates = await self.template_repo.find_by_ids(template_ids, self.user_id)

        if len(templates) != len(template_ids):
            found_ids = {t.id for t in templates}
            missing = set(template_ids) - found_ids
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Templates not found: {list(missing)}")

        inactive = [t.id for t in templates if not t.is_active]
        if inactive:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Templates are inactive: {inactive}")

        drafts = [t.id for t in templates if t.is_draft]
        if drafts:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Templates are drafts: {drafts}")

    async def prepare_job_data(self, job_data: dict) -> dict:
        """Prepare job data with calculated next_run_at."""
        cron_expr, _human = schedule_to_cron(job_data["schedule"])
        timezone = job_data["schedule"].get("timezone", "Europe/Moscow")
        next_run = get_next_run_time(cron_expr, timezone)

        job_data["next_run_at"] = next_run

        return job_data

    async def create_job(self, job_data: dict):
        """Create new automation job with validation."""
        # Check for duplicate name
        existing = await self.job_repo.find_by_name(self.user_id, job_data["name"])
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Automation job with name '{job_data['name']}' already exists",
            )

        quota = await self.validate_quota()
        await self.validate_schedule(job_data["schedule"], quota)
        await self.validate_templates(job_data["template_ids"])

        job_data = await self.prepare_job_data(job_data)

        return await self.job_repo.create(job_data, self.user_id)

    async def update_job(self, job_id: int, updates: dict):
        """Update automation job with validation."""
        job = await self.job_repo.get_by_id(job_id, self.user_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found")

        # Check for duplicate name if name is being changed
        if "name" in updates and updates["name"] is not None and updates["name"] != job.name:
            existing = await self.job_repo.find_by_name(self.user_id, updates["name"])
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Automation job with name '{updates['name']}' already exists",
                )

        if "schedule" in updates:
            quota = await self.get_user_quotas()
            await self.validate_schedule(updates["schedule"], quota)

            cron_expr, _ = schedule_to_cron(updates["schedule"])
            timezone = updates["schedule"].get("timezone", "Europe/Moscow")
            updates["next_run_at"] = get_next_run_time(cron_expr, timezone)

        if "template_ids" in updates:
            await self.validate_templates(updates["template_ids"])

        return await self.job_repo.update(job, updates)
