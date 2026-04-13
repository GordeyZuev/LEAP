"""Configuration utility functions for Celery tasks.

Provides reusable config resolution logic for template-driven pipeline.
"""

from typing import Any, Literal, cast, overload

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.config_repos import UserConfigRepository
from api.repositories.recording_repos import RecordingRepository
from api.repositories.template_repos import OutputPresetRepository, RecordingTemplateRepository
from api.services.config_resolver import ConfigResolver
from database.models import RecordingModel
from database.template_models import OutputPresetModel
from logger import get_logger

logger = get_logger(__name__)


class RuntimeTemplateNotFoundError(ValueError):
    """``manual_override`` requested a template id that does not exist for this user."""


class BoundTemplateNotFoundError(ValueError):
    """Recording has ``template_id`` set but no matching template row for this user."""


class InvalidOutputPresetsError(ValueError):
    """Effective ``output_config`` references missing, inactive, or inconsistent presets."""


def _normalize_output_preset_ids(raw: Any) -> list[int]:
    """Parse ``preset_ids`` from merged output_config; empty list if absent or empty."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InvalidOutputPresetsError("output_config.preset_ids must be a list of positive integers")
    out: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise InvalidOutputPresetsError("output_config.preset_ids must be a list of positive integers")
        if item <= 0:
            raise InvalidOutputPresetsError("output_config.preset_ids must be positive integers")
        out.append(item)
    return out


def _normalize_default_platforms(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InvalidOutputPresetsError("output_config.default_platforms must be a list of strings")
    return [str(p).strip() for p in raw if str(p).strip()]


async def validate_effective_output_config(
    session: AsyncSession,
    user_id: str,
    output_config: dict[str, Any],
) -> None:
    """
    Validate merged output_config: preset ids exist and are active; upload invariants.

    Raises:
        InvalidOutputPresetsError: On unknown ids, inactive presets, or auto_upload/platform mismatch.
    """
    preset_ids = _normalize_output_preset_ids(output_config.get("preset_ids"))
    auto_upload = bool(output_config.get("auto_upload", False))
    default_platforms = _normalize_default_platforms(output_config.get("default_platforms"))

    if auto_upload and default_platforms and not preset_ids:
        raise InvalidOutputPresetsError(
            "auto_upload with default_platforms requires preset_ids; cannot upload without configured presets"
        )

    presets: list[OutputPresetModel] = []
    if preset_ids:
        requested = set(preset_ids)
        preset_repo = OutputPresetRepository(session)
        presets = await preset_repo.find_by_ids(list(requested), user_id)
        found_ids = {p.id for p in presets}
        missing = requested - found_ids
        if missing:
            raise InvalidOutputPresetsError(f"Unknown or inaccessible preset ids: {sorted(missing)}")
        inactive = [p.id for p in presets if not p.is_active]
        if inactive:
            raise InvalidOutputPresetsError(f"Inactive presets cannot be used for upload: {sorted(inactive)}")

    if auto_upload and default_platforms and preset_ids:
        platforms_from_presets = {p.platform.lower() for p in presets}
        for plat in default_platforms:
            if plat.lower() not in platforms_from_presets:
                raise InvalidOutputPresetsError(f"No preset for platform {plat!r} in output_config.preset_ids")


async def validate_runtime_template_override(
    session: AsyncSession,
    user_id: str,
    manual_override: dict[str, Any] | None,
) -> None:
    """
    Ensure ``runtime_template_id`` in ``manual_override`` refers to an existing template.

    Raises:
        RuntimeTemplateNotFoundError: Template id is set (non-None) but not found for ``user_id``.
    """
    if not manual_override or "runtime_template_id" not in manual_override:
        return
    runtime_template_id = manual_override["runtime_template_id"]
    if runtime_template_id is None:
        return
    template_repo = RecordingTemplateRepository(session)
    if not await template_repo.find_by_id(runtime_template_id, user_id):
        raise RuntimeTemplateNotFoundError(f"Template {runtime_template_id} not found")


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
        RuntimeTemplateNotFoundError: If ``manual_override`` references a missing runtime template
        BoundTemplateNotFoundError: If ``recording.template_id`` points to a missing template
        InvalidOutputPresetsError: If merged ``output_config`` is invalid (when ``include_output_config`` is True)
    """
    # Get recording
    recording_repo = RecordingRepository(session)
    recording = await recording_repo.get_by_id(recording_id, user_id)

    if not recording:
        raise ValueError(f"Recording {recording_id} not found")

    await validate_runtime_template_override(session, user_id, manual_override)

    # Get full user config as base
    user_config_repo = UserConfigRepository(session)
    full_config = await user_config_repo.get_effective_config(user_id)

    # Initialize config resolver for merging
    config_resolver = ConfigResolver(session)

    # Merge with bound template if recording.template_id is set (must exist)
    if recording.template_id:
        template_repo = RecordingTemplateRepository(session)
        bound_template = await template_repo.find_by_id(recording.template_id, user_id)
        if not bound_template:
            raise BoundTemplateNotFoundError(
                f"Recording is bound to template {recording.template_id} but template not found"
            )
        if bound_template.processing_config:
            logger.debug(f"Merging recording template '{bound_template.name}' config for recording {recording_id}")
            full_config = config_resolver._merge_configs(full_config, bound_template.processing_config)

    # Merge with runtime template_id (higher priority than recording.template_id)
    runtime_template = None
    if manual_override and "runtime_template_id" in manual_override:
        runtime_template_id = manual_override["runtime_template_id"]
        if runtime_template_id is not None:
            template_repo = RecordingTemplateRepository(session)
            runtime_template = await template_repo.find_by_id(runtime_template_id, user_id)
            if not runtime_template:
                raise RuntimeTemplateNotFoundError(f"Template {runtime_template_id} not found")

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

        await validate_effective_output_config(session, user_id, output_config)

        return full_config, output_config, recording

    return full_config, recording
