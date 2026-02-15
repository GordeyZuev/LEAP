"""Template, config, source and preset repositories"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.template_models import (
    BaseConfigModel,
    InputSourceModel,
    OutputPresetModel,
    RecordingTemplateModel,
)


class BaseConfigRepository:
    """Repository for working with base configurations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: str | None,
        name: str,
        config_data: dict[str, Any],
        description: str | None = None,
        config_type: str | None = None,
    ) -> BaseConfigModel:
        """Create a new configuration."""
        config = BaseConfigModel(
            user_id=user_id,
            name=name,
            description=description,
            config_type=config_type,
            config_data=config_data,
        )
        self.session.add(config)
        await self.session.flush()
        return config

    async def update(self, config: BaseConfigModel) -> BaseConfigModel:
        """Update configuration."""
        config.updated_at = datetime.now(UTC)
        await self.session.flush()
        return config

    async def delete(self, config: BaseConfigModel) -> None:
        """Delete configuration."""
        await self.session.delete(config)
        await self.session.flush()


class InputSourceRepository:
    """Repository for working with data sources."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, source_id: int, user_id: str) -> InputSourceModel | None:
        """Get source by ID with permission check."""
        result = await self.session.execute(
            select(InputSourceModel).where(InputSourceModel.id == source_id, InputSourceModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_active_by_user(self, user_id: str) -> list[InputSourceModel]:
        """Get active sources for user."""
        result = await self.session.execute(
            select(InputSourceModel).where(InputSourceModel.user_id == user_id, InputSourceModel.is_active)
        )
        return list(result.scalars().all())

    async def find_by_user(self, user_id: str) -> list[InputSourceModel]:
        """Get all sources for user (both active and inactive)."""
        result = await self.session.execute(select(InputSourceModel).where(InputSourceModel.user_id == user_id))
        return list(result.scalars().all())

    async def find_duplicate(
        self,
        user_id: str,
        name: str,
        source_type: str,
        credential_id: int | None,
    ) -> InputSourceModel | None:
        """
        Search for a duplicate source.

        A source is considered a duplicate if the user already has a source with the same:
        - name
        - source_type
        - credential_id (optional)
        """
        query = select(InputSourceModel).where(
            InputSourceModel.user_id == user_id,
            InputSourceModel.name == name,
            InputSourceModel.source_type == source_type,
        )

        if credential_id is not None:
            query = query.where(InputSourceModel.credential_id == credential_id)
        else:
            query = query.where(InputSourceModel.credential_id.is_(None))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: str,
        name: str,
        source_type: str,
        credential_id: int | None = None,
        config: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> InputSourceModel:
        """Create a new source."""
        source = InputSourceModel(
            user_id=user_id,
            name=name,
            source_type=source_type,
            credential_id=credential_id,
            config=config,
            description=description,
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def update(self, source: InputSourceModel) -> InputSourceModel:
        """Update source."""
        source.updated_at = datetime.now(UTC)
        await self.session.flush()
        return source

    async def update_last_sync(self, source: InputSourceModel) -> InputSourceModel:
        """Update time of last synchronization."""
        source.last_sync_at = datetime.now(UTC)
        await self.session.flush()
        return source

    async def delete(self, source: InputSourceModel) -> None:
        """Delete source."""
        await self.session.delete(source)
        await self.session.flush()


class OutputPresetRepository:
    """Repository for working with output presets."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, preset_id: int, user_id: str) -> OutputPresetModel | None:
        """Get preset by ID with permission check."""
        result = await self.session.execute(
            select(OutputPresetModel).where(OutputPresetModel.id == preset_id, OutputPresetModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_by_ids(self, preset_ids: list[int], user_id: str) -> list[OutputPresetModel]:
        """Get multiple presets by IDs (batch load to avoid N+1)."""
        if not preset_ids:
            return []

        result = await self.session.execute(
            select(OutputPresetModel).where(
                OutputPresetModel.id.in_(preset_ids),
                OutputPresetModel.user_id == user_id,
            )
        )
        return list(result.scalars().all())

    async def find_active_by_user(self, user_id: str) -> list[OutputPresetModel]:
        """Get active presets for user."""
        result = await self.session.execute(
            select(OutputPresetModel).where(OutputPresetModel.user_id == user_id, OutputPresetModel.is_active)
        )
        return list(result.scalars().all())

    async def find_by_user(self, user_id: str) -> list[OutputPresetModel]:
        """Get all presets for user (both active and inactive)."""
        result = await self.session.execute(select(OutputPresetModel).where(OutputPresetModel.user_id == user_id))
        return list(result.scalars().all())

    async def find_by_name(self, user_id: str, name: str) -> OutputPresetModel | None:
        """Find a preset by user_id and name (for duplicate checking)."""
        result = await self.session.execute(
            select(OutputPresetModel).where(
                OutputPresetModel.user_id == user_id,
                OutputPresetModel.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_platform(self, user_id: str, platform: str) -> list[OutputPresetModel]:
        """Get presets by platform."""
        result = await self.session.execute(
            select(OutputPresetModel).where(
                OutputPresetModel.user_id == user_id,
                OutputPresetModel.platform == platform,
                OutputPresetModel.is_active,
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        user_id: str,
        name: str,
        platform: str,
        credential_id: int,
        preset_metadata: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> OutputPresetModel:
        """Create a new preset."""
        preset = OutputPresetModel(
            user_id=user_id,
            name=name,
            platform=platform,
            credential_id=credential_id,
            preset_metadata=preset_metadata,
            description=description,
        )
        self.session.add(preset)
        await self.session.flush()
        return preset

    async def update(self, preset: OutputPresetModel) -> OutputPresetModel:
        """Update preset."""
        preset.updated_at = datetime.now(UTC)
        await self.session.flush()
        return preset

    async def delete(self, preset: OutputPresetModel) -> None:
        """Delete preset."""
        await self.session.delete(preset)
        await self.session.flush()


class RecordingTemplateRepository:
    """Repository for working with recording templates."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, template_id: int, user_id: str) -> RecordingTemplateModel | None:
        """Get template by ID with permission check."""
        result = await self.session.execute(
            select(RecordingTemplateModel).where(
                RecordingTemplateModel.id == template_id, RecordingTemplateModel.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def find_by_name(self, user_id: str, name: str) -> RecordingTemplateModel | None:
        """Find a template by user_id and name (for duplicate checking)."""
        result = await self.session.execute(
            select(RecordingTemplateModel).where(
                RecordingTemplateModel.user_id == user_id,
                RecordingTemplateModel.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_user(self, user_id: str) -> list[RecordingTemplateModel]:
        """Get active templates for user, sorted by created_at ASC (first-match strategy)."""
        result = await self.session.execute(
            select(RecordingTemplateModel)
            .where(
                RecordingTemplateModel.user_id == user_id,
                RecordingTemplateModel.is_active,
                ~RecordingTemplateModel.is_draft,
            )
            .order_by(RecordingTemplateModel.created_at.asc())
        )
        return list(result.scalars().all())

    async def find_by_user(self, user_id: str, include_drafts: bool = False) -> list[RecordingTemplateModel]:
        """Get all templates for user, sorted by created_at ASC."""
        query = select(RecordingTemplateModel).where(RecordingTemplateModel.user_id == user_id)

        if not include_drafts:
            query = query.where(~RecordingTemplateModel.is_draft)

        query = query.order_by(RecordingTemplateModel.created_at.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_by_ids(self, template_ids: list[int], user_id: str) -> list[RecordingTemplateModel]:
        """Get templates by IDs for user, sorted by created_at ASC."""
        result = await self.session.execute(
            select(RecordingTemplateModel)
            .where(RecordingTemplateModel.user_id == user_id, RecordingTemplateModel.id.in_(template_ids))
            .order_by(RecordingTemplateModel.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        user_id: str,
        name: str,
        matching_rules: dict[str, Any] | None = None,
        processing_config: dict[str, Any] | None = None,
        metadata_config: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
        description: str | None = None,
        is_draft: bool = False,
    ) -> RecordingTemplateModel:
        """Create a new template."""
        template = RecordingTemplateModel(
            user_id=user_id,
            name=name,
            description=description,
            matching_rules=matching_rules,
            processing_config=processing_config,
            metadata_config=metadata_config,
            output_config=output_config,
            is_draft=is_draft,
        )
        self.session.add(template)
        await self.session.flush()
        return template

    async def update(self, template: RecordingTemplateModel) -> RecordingTemplateModel:
        """Update template."""
        template.updated_at = datetime.now(UTC)
        await self.session.flush()
        return template

    async def increment_usage(self, template: RecordingTemplateModel) -> RecordingTemplateModel:
        """Increment usage counter."""
        template.used_count += 1
        template.last_used_at = datetime.now(UTC)
        await self.session.flush()
        return template

    async def delete(self, template: RecordingTemplateModel) -> None:
        """Delete template."""
        await self.session.delete(template)
        await self.session.flush()
