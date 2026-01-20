"""Configuration utility functions for Celery tasks.

Provides reusable config resolution logic for template-driven pipeline.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import RecordingTemplateRepository
from api.services.config_resolver import ConfigResolver
from database.models import RecordingModel
from logger import format_log, get_logger

logger = get_logger(__name__)


async def get_allow_skipped_flag(
    session: AsyncSession,
    user_id: int,
    template_id: int | None = None,
    explicit_value: bool | None = None,
) -> bool:
    """
    Get allow_skipped flag from configuration hierarchy.

    Priority (highest to lowest):
    1. Explicit parameter (explicit_value)
    2. Template.processing_config.allow_skipped
    3. User config.processing.allow_skipped
    4. Default: False

    Args:
        session: DB session
        user_id: User ID
        template_id: Template ID (optional)
        explicit_value: Explicit value from query param

    Returns:
        bool - allow processing of SKIPPED recordings
    """
    # 1. Explicit parameter has highest priority
    if explicit_value is not None:
        return explicit_value

    # 2. Check template (if specified)
    if template_id is not None:
        template_repo = RecordingTemplateRepository(session)
        template = await template_repo.find_by_id(template_id, user_id)
        if template and template.processing_config:
            allow_skipped = template.processing_config.get("allow_skipped")
            if allow_skipped is not None:
                return bool(allow_skipped)

    # 3. Check user config
    try:
        user_config_repo = UserConfigRepository(session)
        user_config_model = await user_config_repo.get_by_user_id(user_id)
        if user_config_model:
            processing_config = user_config_model.config_data.get("processing", {})
            allow_skipped = processing_config.get("allow_skipped")
            if allow_skipped is not None:
                return bool(allow_skipped)
    except Exception as e:
        logger.debug(format_log("Could not get user config", error=str(e)))

    # 4. Default: False (disallow SKIPPED processing)
    return False


async def get_user_processing_config(
    session: AsyncSession,
    user_id: int,
) -> dict[str, Any]:
    """
    Get user's processing configuration.

    Args:
        session: DB session
        user_id: User ID

    Returns:
        dict with processing configuration
    """
    try:
        user_config_repo = UserConfigRepository(session)
        user_config_model = await user_config_repo.get_by_user_id(user_id)
        if user_config_model:
            return user_config_model.config_data.get("processing", {})
    except Exception as e:
        logger.warning(format_log("Could not get user processing config", error=str(e)))

    return {}


async def resolve_full_config(
    session: AsyncSession,
    recording_id: int,
    user_id: int,
    manual_override: dict[str, Any] | None = None,
    include_output_config: bool = False,
) -> tuple[dict[str, Any], RecordingModel] | tuple[dict[str, Any], dict[str, Any], RecordingModel]:
    """
    Resolve full configuration for recording with hierarchy.

    Config hierarchy (lowest to highest priority):
    1. user_config (base defaults)
    2. template.processing_config (if recording.template_id set)
    3. recording.processing_preferences (if exists)
    4. manual_override (highest priority)

    Args:
        session: AsyncSession
        recording_id: Recording ID
        user_id: User ID
        manual_override: Optional manual config override
        include_output_config: If True, also resolve and return output_config

    Returns:
        If include_output_config=False: Tuple of (resolved_config, recording)
        If include_output_config=True: Tuple of (resolved_config, output_config, recording)

    Raises:
        ValueError: If recording not found
    """
    # Get recording
    recording_repo = RecordingRepository(session)
    recording = await recording_repo.get_by_id(recording_id, user_id)

    if not recording:
        raise ValueError(f"Recording {recording_id} not found")

    # Get full user config as base
    user_config_repo = UserConfigRepository(session)
    full_config = await user_config_repo.get_effective_config(user_id)

    # Initialize config resolver for merging
    config_resolver = ConfigResolver(session)

    # Merge with template if exists
    if recording.template_id:
        template_repo = RecordingTemplateRepository(session)
        template = await template_repo.find_by_id(recording.template_id, user_id)
        if template and template.processing_config:
            logger.debug(f"Merging template '{template.name}' config for recording {recording_id}")
            full_config = config_resolver._merge_configs(full_config, template.processing_config)

    # Merge with recording.processing_preferences if exists (higher priority)
    if recording.processing_preferences:
        logger.debug(f"Merging recording.processing_preferences for recording {recording_id}")
        full_config = config_resolver._merge_configs(full_config, recording.processing_preferences)

    # Merge with manual_override (absolute highest priority)
    if manual_override:
        logger.debug(f"Applying manual_override for recording {recording_id}")
        full_config = config_resolver._merge_configs(full_config, manual_override)

    # Flatten nested processing_config structure if exists
    # Templates store: {"processing_config": {"transcription": {...}}}
    # Tasks expect flat: {"transcription": {...}}
    # NOTE: metadata_config and output_config should NOT be flattened!
    if "processing_config" in full_config:
        nested_config = full_config.pop("processing_config")
        full_config = config_resolver._merge_configs(full_config, nested_config)
        logger.debug(f"Flattened nested processing_config for recording {recording_id}")

    logger.info(
        f"Resolved config for recording {recording_id}: "
        f"template_id={recording.template_id}, "
        f"has_preferences={bool(recording.processing_preferences)}, "
        f"has_override={bool(manual_override)}"
    )

    # Optionally include output_config
    if include_output_config:
        output_config = await config_resolver.resolve_output_config(recording, user_id)
        return full_config, output_config, recording

    return full_config, recording
