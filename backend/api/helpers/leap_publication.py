"""Read-time LEAP publication look (title / description / cover). Not stored on recordings."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.helpers.template_renderer import TemplateRenderer, render_jinja
from api.repositories.config_repos import UserConfigRepository
from api.repositories.template_repos import OutputPresetRepository, RecordingTemplateRepository
from api.services.config_utils import is_leap_platform
from api.services.default_template import upload_config_to_output
from api.services.merger import deep_merge
from database.models import RecordingModel
from database.template_models import OutputPresetModel, RecordingTemplateModel
from logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PublicationLook:
    title: str
    description_template: str | None
    thumbnail_name: str | None


def _coerce_positive_int(item: Any) -> int | None:
    if isinstance(item, bool):
        return None
    if isinstance(item, int) and item > 0:
        return item
    if isinstance(item, str) and item.isdigit():
        n = int(item)
        return n if n > 0 else None
    return None


def _as_int_ids(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        n = _coerce_positive_int(item)
        if n is not None:
            out.append(n)
    return out


def _leap_look_meta(leap: OutputPresetModel | None, overlay: Any) -> dict[str, Any] | None:
    """Preset metadata plus template/Run overlay. None when no active leap preset is resolved."""
    if leap is None:
        return None
    leap_meta: dict[str, Any] = {}
    if isinstance(leap.preset_metadata, dict):
        leap_meta = copy.deepcopy(leap.preset_metadata)
    if isinstance(overlay, dict) and overlay:
        leap_meta = deep_merge(leap_meta, overlay, skip_none=True)
    return leap_meta


def _collect_preset_ids(output: dict[str, Any] | None, into: set[int]) -> None:
    if not isinstance(output, dict):
        return
    into.update(_as_int_ids(output.get("preset_ids")))


def _prefs_dict(recording: RecordingModel) -> dict[str, Any]:
    prefs = recording.processing_preferences
    return prefs if isinstance(prefs, dict) else {}


def _active_leap_preset(
    preset_ids: list[int],
    presets_by_id: dict[int, OutputPresetModel],
) -> OutputPresetModel | None:
    for pid in preset_ids:
        preset = presets_by_id.get(pid)
        if preset is None or not is_leap_platform(preset.platform):
            continue
        if not preset.is_active:
            continue
        return preset
    return None


def render_publication_title(
    recording: RecordingModel,
    *,
    leap_meta: dict[str, Any] | None,
    global_title_template: str | None,
) -> str:
    display = recording.display_name or "Unknown"
    template: str | None = None
    if isinstance(leap_meta, dict):
        raw = leap_meta.get("title_template")
        if isinstance(raw, str) and raw.strip():
            template = raw
    if template is None and isinstance(global_title_template, str) and global_title_template.strip():
        template = global_title_template
    if template is None:
        return display
    try:
        rendered = render_jinja(template, TemplateRenderer.prepare_recording_context(recording)).strip()
    except Exception:
        logger.debug("Publication title Jinja failed | rec={}", recording.id)
        return display
    return rendered or display


def _merge_output_and_metadata(
    *,
    default_tpl: RecordingTemplateModel | None,
    bound: RecordingTemplateModel | None,
    runtime: RecordingTemplateModel | None,
    preferences: dict[str, Any],
    user_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if default_tpl and default_tpl.metadata_config:
        metadata = copy.deepcopy(default_tpl.metadata_config)
    else:
        metadata = copy.deepcopy(user_config.get("metadata") or {})

    if default_tpl and default_tpl.output_config:
        output = copy.deepcopy(default_tpl.output_config)
    else:
        output = upload_config_to_output(user_config.get("upload") or {})

    if bound and bound.metadata_config:
        metadata = deep_merge(metadata, bound.metadata_config, skip_none=True)
    if bound and bound.output_config:
        output = deep_merge(output, bound.output_config, skip_none=True)

    if runtime and runtime.metadata_config:
        metadata = deep_merge(metadata, runtime.metadata_config, skip_none=True)
    if runtime and runtime.output_config:
        output = deep_merge(output, runtime.output_config, skip_none=True)

    if isinstance(preferences.get("metadata_config"), dict):
        metadata = deep_merge(metadata, preferences["metadata_config"], skip_none=True)
    if isinstance(preferences.get("output_config"), dict):
        output = deep_merge(output, preferences["output_config"], skip_none=True)

    return output if isinstance(output, dict) else {}, metadata if isinstance(metadata, dict) else {}


async def publication_looks_for_recordings(
    session: AsyncSession,
    user_id: str,
    recordings: list[RecordingModel | None],
) -> dict[int, PublicationLook]:
    recs = [r for r in recordings if r is not None]
    if not recs:
        return {}

    tpl_repo = RecordingTemplateRepository(session)
    default_tpl = await tpl_repo.find_default_by_user(user_id)
    user_config = await UserConfigRepository(session).get_effective_config(user_id)

    template_ids: set[int] = set()
    if default_tpl:
        template_ids.add(default_tpl.id)
    for rec in recs:
        if rec.template_id:
            template_ids.add(rec.template_id)
        prefs = _prefs_dict(rec)
        runtime_id = _coerce_positive_int(prefs.get("runtime_template_id"))
        if runtime_id is not None:
            template_ids.add(runtime_id)

    templates: dict[int, RecordingTemplateModel] = {}
    if template_ids:
        for tpl in await tpl_repo.find_by_ids(list(template_ids), user_id):
            templates[tpl.id] = tpl

    preset_ids: set[int] = set()
    if default_tpl:
        _collect_preset_ids(default_tpl.output_config, preset_ids)
    for tpl in templates.values():
        _collect_preset_ids(tpl.output_config, preset_ids)
    for rec in recs:
        prefs = _prefs_dict(rec)
        _collect_preset_ids(
            prefs.get("output_config") if isinstance(prefs.get("output_config"), dict) else None, preset_ids
        )

    presets_by_id: dict[int, OutputPresetModel] = {}
    if preset_ids:
        for preset in await OutputPresetRepository(session).find_by_ids(list(preset_ids), user_id):
            presets_by_id[preset.id] = preset

    looks: dict[int, PublicationLook] = {}
    for rec in recs:
        prefs = _prefs_dict(rec)
        bound = templates.get(rec.template_id) if rec.template_id else None
        if bound and default_tpl and bound.id == default_tpl.id:
            bound = None
        runtime_id = _coerce_positive_int(prefs.get("runtime_template_id"))
        runtime = templates.get(runtime_id) if runtime_id is not None else None
        if runtime and default_tpl and runtime.id == default_tpl.id:
            runtime = None
        output, metadata = _merge_output_and_metadata(
            default_tpl=default_tpl,
            bound=bound,
            runtime=runtime,
            preferences=prefs,
            user_config=user_config,
        )
        leap = _active_leap_preset(_as_int_ids(output.get("preset_ids")), presets_by_id)
        look_meta = _leap_look_meta(leap, metadata.get("leap"))
        title = render_publication_title(
            rec,
            leap_meta=look_meta,
            global_title_template=metadata.get("title_template")
            if isinstance(metadata.get("title_template"), str)
            else None,
        )
        desc_t = None
        thumb = None
        if look_meta:
            raw_desc = look_meta.get("description_template")
            if isinstance(raw_desc, str) and raw_desc.strip():
                desc_t = raw_desc
            raw_thumb = look_meta.get("thumbnail_name")
            if isinstance(raw_thumb, str) and raw_thumb.strip():
                thumb = raw_thumb.strip()
        looks[rec.id] = PublicationLook(title=title, description_template=desc_t, thumbnail_name=thumb)
    return looks
