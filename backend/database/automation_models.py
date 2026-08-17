"""Database models for recording automation"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship

from database.models import Base


class AutomationJobModel(Base):
    """Automation job for scheduled recording sync and processing"""

    __tablename__ = "automation_jobs"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_automation_jobs_user_name"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    template_ids = Column(ARRAY(Integer), nullable=False, server_default="{}")

    schedule = Column(JSONB, nullable=False)
    sync_config = Column(JSONB, nullable=False)
    filters = Column(JSONB, nullable=True)
    processing_config = Column(JSONB, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    run_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    user = relationship("UserModel", back_populates="automation_jobs")
    runs = relationship(
        "AutomationJobRunModel",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<AutomationJob(id={self.id}, user_id={self.user_id}, name='{self.name}', active={self.is_active})>"


class AutomationJobRunModel(Base):
    """One execution of an automation job.

    Without this a scheduled job is unverifiable: the job row only carries
    ``last_run_at``, so a run that failed at 3am looks the same as one that
    processed nothing.
    """

    __tablename__ = "automation_job_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # SUCCESS | FAILED | SKIPPED — what the task returned.
    status = Column(String(20), nullable=False)
    # SCHEDULE | MANUAL — how the run was triggered.
    trigger = Column(String(20), nullable=False, default="SCHEDULE")

    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=True)

    synced_count = Column(Integer, nullable=False, default=0)
    recordings_found = Column(Integer, nullable=False, default=0)
    matched_count = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)

    error = Column(Text, nullable=True)

    job = relationship("AutomationJobModel", back_populates="runs")

    def __repr__(self):
        return f"<AutomationJobRun(id={self.id}, job_id={self.job_id}, status='{self.status}')>"
