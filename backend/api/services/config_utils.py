"""Configuration utility functions for Celery tasks.

Provides reusable config resolution logic for template-driven pipeline.
"""

from typing import Any, Literal, overload

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
    template = await template_repo.find_by_id(runtime_template_id, user_id)
    if not template:
        raise RuntimeTemplateNotFoundError(f"Template {runtime_template_id} not found")
    if getattr(template, "is_default", False):
        raise RuntimeTemplateNotFoundError("runtime_template_id cannot reference the default template")


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
    Resolve full configuration for recording — thin wrapper over ``ConfigResolver.resolve``.

    Returns flat processing keys (``trimming``, ``transcription``) plus account ``download``
    and resolved ``metadata_config`` for pipeline tasks.
    """
    from api.services.config_resolver import ResolveContext

    recording_repo = RecordingRepository(session)
    recording = await recording_repo.get_by_id(recording_id, user_id)

    if not recording:
        raise ValueError(f"Recording {recording_id} not found")

    await validate_runtime_template_override(session, user_id, manual_override)

    if recording.template_id:
        template_repo = RecordingTemplateRepository(session)
        if not await template_repo.find_by_id(recording.template_id, user_id):
            raise BoundTemplateNotFoundError(
                f"Recording is bound to template {recording.template_id} but template not found"
            )

    resolver = ConfigResolver(session)
    resolved = await resolver.resolve(
        ResolveContext(user_id=user_id, recording=recording, manual_override=manual_override)
    )

    user_config_repo = UserConfigRepository(session)
    user_config = await user_config_repo.get_effective_config(user_id)

    import copy

    full_config: dict[str, Any] = copy.deepcopy(resolved.processing)
    if isinstance(user_config.get("download"), dict):
        full_config["download"] = copy.deepcopy(user_config["download"])
    full_config["metadata_config"] = copy.deepcopy(resolved.metadata)

    logger.info(
        "Resolved config for recording %s: template_id=%s, has_preferences=%s, has_override=%s",
        recording_id,
        recording.template_id,
        bool(recording.processing_preferences),
        bool(manual_override),
    )

    if include_output_config:
        await validate_effective_output_config(session, user_id, resolved.output)
        return full_config, resolved.output, recording

    return full_config, recording
