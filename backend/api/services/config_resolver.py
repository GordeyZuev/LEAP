"""Service for resolving recording configuration hierarchy.

Merge order (lowest → highest priority):

Processing (flat ``trimming`` + ``transcription`` for workers):
  default_template → bound_template → runtime_template → preferences → manual_override

Metadata / output: same layer order; ``preferences`` keys are deep-merged, not replaced.

Account-only keys (``retention``, ``download``, ``platforms``) live in ``user_configs`` and are
not part of this resolver.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.config_repos import UserConfigRepository
from api.repositories.template_repos import OutputPresetRepository, RecordingTemplateRepository
from api.services.default_template import upload_config_to_output
from api.services.merger import deep_merge
from database.models import RecordingModel
from database.template_models import RecordingTemplateModel
from logger import get_logger

logger = get_logger()


def extract_thumbnail_name_from_metadata(metadata: dict[str, Any]) -> str | None:
    """Pick a thumbnail filename from resolved metadata_config for UI preview."""
    for platform in ("youtube", "vk"):
        block = metadata.get(platform)
        if isinstance(block, dict):
            name = block.get("thumbnail_name")
            if isinstance(name, str) and name.strip():
                return name.strip()

    common = metadata.get("thumbnail_name")
    if isinstance(common, str) and common.strip():
        return common.strip()

    return None


def _processing_slice_from_user_config(user_config: dict[str, Any]) -> dict[str, Any]:
    """Flat processing dict from legacy user_config (pre-default-template)."""
    result: dict[str, Any] = {}
    if isinstance(user_config.get("trimming"), dict):
        result["trimming"] = copy.deepcopy(user_config["trimming"])
    if isinstance(user_config.get("transcription"), dict):
        result["transcription"] = copy.deepcopy(user_config["transcription"])
    return result


def _merge_template_processing_block(
    base: dict[str, Any], template_processing: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge template ``processing_config`` into flat processing dict."""
    if not template_processing:
        return base
    result = deep_merge(base, template_processing, skip_none=True)
    vocab = template_processing.get("transcription_vocabulary")
    if isinstance(vocab, list) and vocab:
        trans = result.setdefault("transcription", {})
        if isinstance(trans, dict):
            existing = trans.get("vocabulary") or []
            merged = list(existing) if isinstance(existing, list) else []
            for term in vocab:
                if isinstance(term, str) and term.strip() and term.strip() not in merged:
                    merged.append(term.strip())
            trans["vocabulary"] = merged
    return result


def _preferences_processing_slice(preferences: dict[str, Any] | None) -> dict[str, Any]:
    if not preferences:
        return {}
    if isinstance(preferences.get("processing_config"), dict):
        return copy.deepcopy(preferences["processing_config"])
    legacy_keys = ("trimming", "transcription", "transcription_vocabulary")
    return {k: copy.deepcopy(preferences[k]) for k in legacy_keys if k in preferences}


@dataclass
class ConfigLayer:
    source: str
    config: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    name: str | None = None


@dataclass
class ResolvedConfig:
    processing: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    layers: list[ConfigLayer] = field(default_factory=list)


@dataclass
class ResolveContext:
    user_id: str
    recording: RecordingModel | None = None
    preview_template_id: int | None = None
    manual_override: dict[str, Any] | None = None
    include_layers: bool = False


class ConfigResolver:
    """Resolve effective configuration from default template, bound/runtime templates, and overrides."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_config_repo = UserConfigRepository(session)
        self.template_repo = RecordingTemplateRepository(session)
        self.preset_repo = OutputPresetRepository(session)

    async def resolve(self, ctx: ResolveContext) -> ResolvedConfig:
        """Resolve processing, metadata, and output with unified merge order."""
        layers: list[ConfigLayer] = []
        user_config = await self._get_user_config(ctx.user_id)

        default_tpl = await self.template_repo.find_default_by_user(ctx.user_id)
        bound_tpl: RecordingTemplateModel | None = None
        runtime_tpl: RecordingTemplateModel | None = None
        preferences: dict[str, Any] = {}

        if ctx.recording:
            preferences = ctx.recording.processing_preferences or {}
            if ctx.recording.template_id:
                bound_tpl = await self.template_repo.find_by_id(ctx.recording.template_id, ctx.user_id)

        preview_tpl: RecordingTemplateModel | None = None
        if ctx.preview_template_id is not None:
            preview_tpl = await self.template_repo.find_by_id(ctx.preview_template_id, ctx.user_id)

        if ctx.manual_override and "runtime_template_id" in ctx.manual_override:
            runtime_id = ctx.manual_override["runtime_template_id"]
            if runtime_id is not None:
                runtime_tpl = await self.template_repo.find_by_id(runtime_id, ctx.user_id)
                if runtime_tpl and getattr(runtime_tpl, "is_default", False):
                    raise ValueError("runtime_template_id cannot reference the default template")

        # --- Processing ---
        if default_tpl:
            processing = _merge_template_processing_block({}, default_tpl.processing_config or {})
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(
                        source="default_template",
                        id=default_tpl.id,
                        name=default_tpl.name,
                        config={"processing_config": copy.deepcopy(default_tpl.processing_config or {})},
                    )
                )
        else:
            processing = _processing_slice_from_user_config(user_config)
            if ctx.include_layers and processing:
                layers.append(ConfigLayer(source="user_config", config=copy.deepcopy(processing)))

        active_bound = bound_tpl if ctx.recording else preview_tpl
        if active_bound and default_tpl and active_bound.id == default_tpl.id:
            active_bound = None

        if active_bound and active_bound.processing_config:
            processing = _merge_template_processing_block(processing, active_bound.processing_config)
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(
                        source="bound_template" if ctx.recording else "preview_template",
                        id=active_bound.id,
                        name=active_bound.name,
                        config={"processing_config": copy.deepcopy(active_bound.processing_config)},
                    )
                )

        if runtime_tpl and runtime_tpl.processing_config:
            processing = _merge_template_processing_block(processing, runtime_tpl.processing_config)
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(
                        source="runtime_template",
                        id=runtime_tpl.id,
                        name=runtime_tpl.name,
                        config={"processing_config": copy.deepcopy(runtime_tpl.processing_config)},
                    )
                )

        pref_processing = _preferences_processing_slice(preferences)
        if pref_processing:
            processing = _merge_template_processing_block(processing, pref_processing)
            if ctx.include_layers:
                layers.append(ConfigLayer(source="preferences", config={"processing_config": pref_processing}))

        if ctx.manual_override:
            filtered = {k: v for k, v in ctx.manual_override.items() if k != "runtime_template_id"}
            manual_processing = {
                k: v
                for k, v in filtered.items()
                if k in ("trimming", "transcription", "transcription_vocabulary", "processing_config")
            }
            if "processing_config" in manual_processing:
                processing = _merge_template_processing_block(processing, manual_processing.pop("processing_config"))
            if manual_processing:
                processing = _merge_template_processing_block(processing, manual_processing)
            if ctx.include_layers and manual_processing:
                layers.append(ConfigLayer(source="manual_override", config=copy.deepcopy(manual_processing)))

        # --- Metadata ---
        if default_tpl and default_tpl.metadata_config:
            metadata = copy.deepcopy(default_tpl.metadata_config)
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(
                        source="default_template",
                        id=default_tpl.id,
                        name=default_tpl.name,
                        config={"metadata_config": copy.deepcopy(default_tpl.metadata_config)},
                    )
                )
        else:
            metadata = copy.deepcopy(user_config.get("metadata") or {})
            if ctx.include_layers and metadata:
                layers.append(ConfigLayer(source="user_config", config={"metadata_config": copy.deepcopy(metadata)}))

        if active_bound and active_bound.metadata_config:
            metadata = deep_merge(metadata, active_bound.metadata_config, skip_none=True)
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(
                        source="bound_template" if ctx.recording else "preview_template",
                        id=active_bound.id,
                        name=active_bound.name,
                        config={"metadata_config": copy.deepcopy(active_bound.metadata_config)},
                    )
                )

        if runtime_tpl and runtime_tpl.metadata_config:
            metadata = deep_merge(metadata, runtime_tpl.metadata_config, skip_none=True)
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(
                        source="runtime_template",
                        id=runtime_tpl.id,
                        name=runtime_tpl.name,
                        config={"metadata_config": copy.deepcopy(runtime_tpl.metadata_config)},
                    )
                )

        if isinstance(preferences.get("metadata_config"), dict):
            metadata = deep_merge(metadata, preferences["metadata_config"], skip_none=True)
            if ctx.include_layers:
                layers.append(
                    ConfigLayer(source="preferences", config={"metadata_config": preferences["metadata_config"]})
                )

        if ctx.manual_override and isinstance(ctx.manual_override.get("metadata_config"), dict):
            metadata = deep_merge(metadata, ctx.manual_override["metadata_config"], skip_none=True)

        # --- Output ---
        if default_tpl and default_tpl.output_config:
            output = copy.deepcopy(default_tpl.output_config)
        else:
            output = upload_config_to_output(user_config.get("upload") or {})

        if active_bound and active_bound.output_config:
            output = deep_merge(output, active_bound.output_config, skip_none=True)

        if runtime_tpl and runtime_tpl.output_config:
            output = deep_merge(output, runtime_tpl.output_config, skip_none=True)

        if isinstance(preferences.get("output_config"), dict):
            output = deep_merge(output, preferences["output_config"], skip_none=True)

        if ctx.manual_override and isinstance(ctx.manual_override.get("output_config"), dict):
            output = deep_merge(output, ctx.manual_override["output_config"], skip_none=True)

        return ResolvedConfig(processing=processing, metadata=metadata, output=output, layers=layers)

    async def resolve_processing_config(self, recording: RecordingModel, user_id: str) -> dict[str, Any]:
        """Return flat processing config (trimming + transcription) for stage sync and legacy callers."""
        resolved = await self.resolve(ResolveContext(user_id=user_id, recording=recording))
        return resolved.processing

    async def get_base_config_for_edit(self, recording: RecordingModel, user_id: str) -> dict[str, Any]:
        """Resolved bundles for GET /recordings/{id}/config."""
        resolved = await self.resolve(ResolveContext(user_id=user_id, recording=recording))
        template_name = None
        if recording.template_id:
            template = await self.template_repo.find_by_id(recording.template_id, user_id)
            if template:
                template_name = template.name

        processing_config = resolved.processing
        if "transcription" in processing_config or "trimming" in processing_config:
            nested = {}
            if "transcription" in processing_config:
                nested["transcription"] = processing_config["transcription"]
            if "trimming" in processing_config:
                nested["trimming"] = processing_config["trimming"]
            if "transcription_vocabulary" in processing_config:
                nested["transcription_vocabulary"] = processing_config["transcription_vocabulary"]
            processing_config = nested

        return {
            "processing_config": processing_config,
            "output_config": resolved.output,
            "metadata_config": resolved.metadata,
            "has_manual_override": bool(recording.processing_preferences),
            "template_name": template_name,
            "template_id": recording.template_id,
        }

    async def resolve_output_config(self, recording: RecordingModel, user_id: str) -> dict[str, Any]:
        resolved = await self.resolve(ResolveContext(user_id=user_id, recording=recording))
        return resolved.output

    async def resolve_metadata_config(self, recording: RecordingModel, user_id: str) -> dict[str, Any]:
        resolved = await self.resolve(ResolveContext(user_id=user_id, recording=recording))
        return resolved.metadata

    async def resolve_upload_metadata(
        self,
        recording: RecordingModel,
        user_id: str,
        preset_id: int,
    ) -> dict[str, Any]:
        """Resolve upload metadata: preset → default/bound template metadata → preferences."""
        preset = await self.preset_repo.find_by_id(preset_id, user_id)
        if not preset:
            raise ValueError(f"Preset {preset_id} not found for user {user_id}")

        final_metadata = copy.deepcopy(preset.preset_metadata or {})
        resolved = await self.resolve(ResolveContext(user_id=user_id, recording=recording))
        template_meta = resolved.metadata

        platform_key = preset.platform.lower()
        platform_keys = {"youtube", "vk", "yandex_disk", "common"}
        common_fields = {k: v for k, v in template_meta.items() if k not in platform_keys}
        if common_fields:
            final_metadata = deep_merge(final_metadata, common_fields, skip_none=True)

        common_block = template_meta.get("common")
        if isinstance(common_block, dict):
            final_metadata = deep_merge(final_metadata, common_block, skip_none=True)

        platform_block = template_meta.get(platform_key)
        if isinstance(platform_block, dict):
            final_metadata = deep_merge(final_metadata, platform_block, skip_none=True)

        logger.debug(
            "[Metadata Resolution] Final metadata keys for recording %s: %s",
            recording.id,
            list(final_metadata.keys()),
        )
        return final_metadata

    async def _get_user_config(self, user_id: str) -> dict[str, Any]:
        try:
            return await self.user_config_repo.get_effective_config(user_id)
        except Exception as exc:
            logger.warning("Failed to get user config for user %s: %s", user_id, exc)
            return {}

    def _merge_configs(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias; prefer ``deep_merge(..., skip_none=True)``."""
        return deep_merge(base, override, skip_none=True)
