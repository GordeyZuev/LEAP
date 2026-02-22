"""Configuration utility functions for Celery tasks.

Provides reusable config resolution logic for template-driven pipeline.
"""

from typing import Any, Literal, cast, overload

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import RecordingTemplateRepository
from api.services.config_resolver import ConfigResolver
from database.models import RecordingModel
from logger import get_logger

logger = get_logger(__name__)


@overload
async def resolve_full_config(
    session: AsyncSession,
    recording_id: int,
    user_id: str,
    manual_override: dict[str, Any] | None = None,
    *,
    include_output_config: Literal[True],
) -> tuple[dict[str, Any], dict[str, Any], RecordingModel]: ...


@overload
async def resolve_full_config(
    session: AsyncSession,
    recording_id: int,
    user_id: str,
    manual_override: dict[str, Any] | None = None,
    *,
    include_output_config: Literal[False] = False,
) -> tuple[dict[str, Any], RecordingModel]: ...


async def resolve_full_config(
    session: AsyncSession,
    recording_id: int,
    user_id: str,
    manual_override: dict[str, Any] | None = None,
    include_output_config: bool = False,
) -> tuple[dict[str, Any], RecordingModel] | tuple[dict[str, Any], dict[str, Any], RecordingModel]:
    """
    Resolve full configuration for recording with hierarchy.

    Config hierarchy (lowest to highest priority):
    1. user_config (base defaults)
    2. template.processing_config (if recording.template_id set)
    3. runtime_template_id (if provided in manual_override)
    4. recording.processing_preferences (if exists)
    5. manual_override (highest priority)

    Args:
        session: AsyncSession
        recording_id: Recording ID
        user_id: User ID
        manual_override: Optional manual config override (can include runtime_template_id)
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
            logger.debug(f"Merging recording template '{template.name}' config for recording {recording_id}")
            full_config = config_resolver._merge_configs(full_config, template.processing_config)

    # Merge with runtime template_id (higher priority than recording.template_id)
    runtime_template = None
    if manual_override and "runtime_template_id" in manual_override:
        runtime_template_id = manual_override["runtime_template_id"]
        template_repo = RecordingTemplateRepository(session)
        runtime_template = await template_repo.find_by_id(runtime_template_id, user_id)

        if runtime_template:
            logger.info(
                f"Applying runtime template '{runtime_template.name}' (id={runtime_template_id}) "
                f"for recording {recording_id}"
            )
            if runtime_template.processing_config:
                full_config = config_resolver._merge_configs(
                    full_config, cast("dict", runtime_template.processing_config)
                )
            if runtime_template.metadata_config:
                # Wrap metadata_config to preserve structure
                full_config = config_resolver._merge_configs(
                    full_config, {"metadata_config": runtime_template.metadata_config}
                )
        else:
            logger.warning(f"Runtime template_id={runtime_template_id} not found for user {user_id}")

    # Merge with recording.processing_preferences if exists (higher priority)
    if recording.processing_preferences:
        logger.debug(f"Merging recording.processing_preferences for recording {recording_id}")
        full_config = config_resolver._merge_configs(full_config, recording.processing_preferences)

    # Merge with manual_override (absolute highest priority)
    # Filter out runtime_template_id - it's not part of config, just a resolver hint
    if manual_override:
        logger.debug(f"Applying manual_override for recording {recording_id}")
        filtered_override = {k: v for k, v in manual_override.items() if k != "runtime_template_id"}
        if filtered_override:
            full_config = config_resolver._merge_configs(full_config, filtered_override)

    # Flatten nested processing_config structure if exists
    # Templates store: {"processing_config": {"transcription": {...}}}
    # Tasks expect flat: {"transcription": {...}}
    # NOTE: metadata_config and output_config should NOT be flattened!
    if "processing_config" in full_config:
        nested_config = full_config.pop("processing_config")
        full_config = config_resolver._merge_configs(full_config, nested_config)
        logger.debug(f"Flattened nested processing_config for recording {recording_id}")

    # Merge transcription_vocabulary (template-level field) into transcription.vocabulary
    if "transcription_vocabulary" in full_config:
        vocab = full_config.pop("transcription_vocabulary")
        if isinstance(vocab, list) and vocab:
            trans = full_config.setdefault("transcription", {})
            if isinstance(trans, dict):
                existing = trans.get("vocabulary") or []
                merged = list(existing) if isinstance(existing, list) else []
                for v in vocab:
                    if isinstance(v, str) and v.strip() and v.strip() not in merged:
                        merged.append(v.strip())
                trans["vocabulary"] = merged

    logger.info(
        f"Resolved config for recording {recording_id}: "
        f"template_id={recording.template_id}, "
        f"has_preferences={bool(recording.processing_preferences)}, "
        f"has_override={bool(manual_override)}"
    )

    # Optionally include output_config
    if include_output_config:
        output_config = await config_resolver.resolve_output_config(recording, user_id)

        # Apply runtime template output_config if provided (reuse already fetched template)
        if runtime_template and runtime_template.output_config:
            logger.debug(
                f"Applying runtime template output_config from template {runtime_template.id} "
                f"for recording {recording_id}"
            )
            output_config = config_resolver._merge_configs(output_config, cast("dict", runtime_template.output_config))

        # Apply manual output_config override if provided
        if manual_override and "output_config" in manual_override:
            output_config = config_resolver._merge_configs(output_config, manual_override["output_config"])

        return full_config, output_config, recording

    return full_config, recording
