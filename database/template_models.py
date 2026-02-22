"""Database models for templates, configs, sources and presets"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models import Base


class BaseConfigModel(Base):
    """Base configuration (global or user-specific)"""

    __tablename__ = "base_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    config_type = Column(String(50), nullable=True, index=True)
    config_data = Column(JSONB, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self):
        scope = "global" if self.user_id is None else f"user_{self.user_id}"
        return f"<BaseConfig(id={self.id}, name='{self.name}', scope={scope})>"


class InputSourceModel(Base):
    """Input source for recording synchronization."""

    __tablename__ = "input_sources"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "name", "source_type", "credential_id", name="uq_input_sources_user_name_type_credential"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_credentials.id", ondelete="SET NULL"), nullable=True
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    credential = relationship("UserCredentialModel", foreign_keys=[credential_id])

    def __repr__(self):
        return f"<InputSource(id={self.id}, name='{self.name}', type={self.source_type}, user_id={self.user_id})>"


class OutputPresetModel(Base):
    """Output preset for platform uploads."""

    __tablename__ = "output_presets"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_presets_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_credentials.id", ondelete="CASCADE"), nullable=False
    )
    preset_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    credential = relationship("UserCredentialModel", foreign_keys=[credential_id])

    def __repr__(self):
        return f"<OutputPreset(id={self.id}, name='{self.name}', platform={self.platform}, user_id={self.user_id})>"


class RecordingTemplateModel(Base):
    """Template for automatic recording processing."""

    __tablename__ = "recording_templates"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_templates_user_name"),)

    # --- PK & FK ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # --- Core info ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Configuration (JSONB) ---
    matching_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    processing_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Usage stats ---
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self):
        draft_status = " (draft)" if self.is_draft else ""
        return f"<RecordingTemplate(id={self.id}, name='{self.name}', user_id={self.user_id}{draft_status})>"
