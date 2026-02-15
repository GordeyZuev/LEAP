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

    def __repr__(self):
        return f"<AutomationJob(id={self.id}, user_id={self.user_id}, name='{self.name}', active={self.is_active})>"
