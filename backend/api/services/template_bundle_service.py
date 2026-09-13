"""Export/import and full replace for recording template JSON bundles."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.template_repos import InputSourceRepository, OutputPresetRepository, RecordingTemplateRepository
from api.schemas.template.bundle import (
    BundleReference,
    BundleReferencePlaylist,
    BundleReferencePreset,
    BundleReferenceSource,
    RecordingTemplateReplace,
    TemplateBundleExport,
    TemplateBundleExportItem,
    TemplateBundleImport,
    TemplateBundleImportItem,
    TemplateImportErrorItem,
    TemplateImportResult,
    TemplateImportResultItem,
    TemplateImportWarningItem,
)
from api.schemas.template.matching_rules import MatchingRules
from api.schemas.template.metadata_config import TemplateMetadataConfig
from api.schemas.template.output_config import TemplateOutputConfig, normalize_output_config
from api.schemas.template.processing_config import TemplateProcessingConfig
from api.schemas.template.validation import (
    collect_template_warnings,
    matching_rules_has_content,
    validate_template_state,
)
from api.services.config_utils import InvalidOutputPresetsError, is_leap_platform, validate_effective_output_config
from api.services.quota_service import QuotaService
from database.playlist_models import PlaylistModel
from database.template_models import RecordingTemplateModel

BUNDLE_VERSION = 1
_READ_ONLY_TEMPLATE_KEYS = frozenset(
    {"user_id", "used_count", "last_used_at", "created_at", "updated_at", "is_default"}
)
_LEGACY_SINGLE_BRACE = re.compile(r"(?<!\{)\{(?!\{)[^}]+\}")

TemplateBundleError = ValueError


def _strip_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nulls(v) for v in value]
    return value


def _check_legacy_metadata_templates(item: dict[str, Any]) -> None:
    meta = item.get("metadata_config")
    if not isinstance(meta, dict):
        return
    for key in ("title_template", "description_template"):
        text = meta.get(key)
        if isinstance(text, str) and _LEGACY_SINGLE_BRACE.search(text):
            raise TemplateBundleError(
                f"metadata_config.{key} uses legacy single-brace placeholders; use Jinja2 {{ var }} "
                "(see backend/docs/guides/TEMPLATE_JSON.md)"
            )
    for platform in ("youtube", "vk", "leap", "yandex_disk"):
        block = meta.get(platform)
        if not isinstance(block, dict):
            continue
        for key in ("title_template", "description_template", "folder_path_template", "filename_template"):
            text = block.get(key)
            if isinstance(text, str) and _LEGACY_SINGLE_BRACE.search(text):
                raise TemplateBundleError(
                    f"metadata_config.{platform}.{key} uses legacy single-brace placeholders; use Jinja2 {{ var }}"
                )


def _sanitize_template_dict(raw: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in raw.items() if k not in _READ_ONLY_TEMPLATE_KEYS}
    return _strip_nulls(out)


def normalize_raw_to_bundle_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept envelope, {templates: [...]}, or a single template object."""
    if raw.get("leap_template_bundle") == BUNDLE_VERSION and "templates" in raw:
        payload = dict(raw)
    elif "templates" in raw and isinstance(raw["templates"], list):
        payload = {"leap_template_bundle": BUNDLE_VERSION, "templates": raw["templates"]}
    elif "name" in raw:
        payload = {"leap_template_bundle": BUNDLE_VERSION, "templates": [_sanitize_template_dict(raw)]}
    else:
        raise TemplateBundleError("Expected leap_template_bundle object, { templates: [...] }, or a single template")

    templates = payload.get("templates")
    if not isinstance(templates, list) or len(templates) == 0:
        raise TemplateBundleError("templates must be a non-empty array")

    cleaned_templates: list[dict[str, Any]] = []
    for entry in templates:
        if not isinstance(entry, dict):
            raise TemplateBundleError("Each template must be an object")
        item = _sanitize_template_dict(entry)
        _check_legacy_metadata_templates(item)
        cleaned_templates.append(item)

    payload["templates"] = cleaned_templates
    payload.pop("reference", None)
    payload.setdefault("leap_template_bundle", BUNDLE_VERSION)
    return payload


def template_to_export_item(model: RecordingTemplateModel) -> TemplateBundleExportItem:
    matching = MatchingRules.model_validate(model.matching_rules) if model.matching_rules else None
    processing = TemplateProcessingConfig.model_validate(model.processing_config) if model.processing_config else None
    metadata = TemplateMetadataConfig.model_validate(model.metadata_config) if model.metadata_config else None
    output = (
        TemplateOutputConfig.model_validate(normalize_output_config(model.output_config))
        if model.output_config
        else None
    )
    return TemplateBundleExportItem(
        id=model.id,
        name=model.name,
        description=model.description,
        is_draft=model.is_draft,
        is_active=model.is_active,
        is_default=model.is_default,
        matching_rules=matching,
        processing_config=processing,
        metadata_config=metadata,
        output_config=output,
    )


async def build_reference(
    session: AsyncSession, user_id: str, items: list[TemplateBundleExportItem]
) -> BundleReference:
    preset_ids: set[int] = set()
    source_ids: set[int] = set()
    playlist_ids: set[int] = set()

    for item in items:
        output = item.output_config.model_dump() if item.output_config else {}
        for pid in output.get("preset_ids") or []:
            if isinstance(pid, int) and pid > 0:
                preset_ids.add(pid)
        for plid in output.get("playlist_ids") or []:
            if isinstance(plid, int) and plid > 0:
                playlist_ids.add(plid)
        rules = item.matching_rules
        if rules and rules.source_ids:
            for sid in rules.source_ids:
                if sid > 0:
                    source_ids.add(sid)

    preset_repo = OutputPresetRepository(session)
    presets_loaded = await preset_repo.find_by_ids(list(preset_ids), user_id) if preset_ids else []
    presets_by_id = {p.id: p for p in presets_loaded}
    for preset in presets_loaded:
        if is_leap_platform(preset.platform):
            meta = preset.preset_metadata or {}
            for plid in meta.get("playlist_ids") or []:
                if isinstance(plid, int) and plid > 0:
                    playlist_ids.add(plid)

    source_repo = InputSourceRepository(session)
    sources_out: list[BundleReferenceSource] = []
    for sid in sorted(source_ids):
        src = await source_repo.find_by_id(sid, user_id)
        sources_out.append(
            BundleReferenceSource(id=sid, name=src.name if src else None, missing=src is None),
        )

    presets_out: list[BundleReferencePreset] = []
    for pid in sorted(preset_ids):
        preset = presets_by_id.get(pid)
        presets_out.append(
            BundleReferencePreset(
                id=pid,
                name=preset.name if preset else None,
                platform=preset.platform if preset else None,
                missing=preset is None,
            ),
        )

    playlists_out: list[BundleReferencePlaylist] = []
    if playlist_ids:
        result = await session.execute(
            select(PlaylistModel).where(
                PlaylistModel.id.in_(list(playlist_ids)),
                PlaylistModel.user_id == user_id,
            )
        )
        playlists_by_id = {p.id: p for p in result.scalars().all()}
        for plid in sorted(playlist_ids):
            pl = playlists_by_id.get(plid)
            playlists_out.append(
                BundleReferencePlaylist(id=plid, name=pl.name if pl else None, missing=pl is None),
            )

    return BundleReference(presets=presets_out, sources=sources_out, playlists=playlists_out)


async def export_templates_bundle(session: AsyncSession, user_id: str, template_ids: list[int]) -> TemplateBundleExport:
    if not template_ids:
        raise TemplateBundleError("At least one template id is required")
    unique_ids = list(dict.fromkeys(template_ids))
    repo = RecordingTemplateRepository(session)
    models = await repo.find_by_ids(unique_ids, user_id)
    found = {m.id for m in models}
    missing = set(unique_ids) - found
    if missing:
        raise TemplateBundleError(f"Unknown or inaccessible template ids: {sorted(missing)}")

    order = {tid: idx for idx, tid in enumerate(unique_ids)}
    models.sort(key=lambda m: order.get(m.id, m.id))
    items = [template_to_export_item(m) for m in models]
    reference = await build_reference(session, user_id, items)
    return TemplateBundleExport(
        exported_at=datetime.now(UTC),
        reference=reference,
        templates=items,
    )


def _config_dump(
    model: TemplateBundleImportItem | RecordingTemplateReplace,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    matching = model.matching_rules.model_dump(exclude_none=True) if model.matching_rules else None
    processing = model.processing_config.model_dump(exclude_none=True) if model.processing_config else None
    metadata = model.metadata_config.model_dump(exclude_none=True) if model.metadata_config else None
    output = model.output_config.model_dump(exclude_none=True) if model.output_config else None
    return matching, processing, metadata, output


async def replace_template(
    session: AsyncSession,
    user_id: str,
    template_id: int,
    data: RecordingTemplateReplace,
) -> RecordingTemplateModel:
    repo = RecordingTemplateRepository(session)
    template = await repo.find_by_id(template_id, user_id)
    if not template:
        raise TemplateBundleError(f"Template {template_id} not found")

    if template.is_default:
        if data.is_active is False or data.is_draft is True:
            raise TemplateBundleError("Cannot deactivate or draft the default (base) template")
        if matching_rules_has_content(data.matching_rules):
            raise TemplateBundleError("Default template cannot have matching rules")

    if data.name != template.name:
        existing = await repo.find_by_name(user_id, data.name)
        if existing and existing.id != template_id:
            raise TemplateBundleError(f"Template with name '{data.name}' already exists")

    data.validate_business_rules(is_default=template.is_default)
    output_dump = data.output_config.model_dump(exclude_none=True) if data.output_config else None
    await validate_effective_output_config(session, user_id, output_dump or {})

    matching, processing, metadata, output = _config_dump(data)
    template.name = data.name
    template.description = data.description
    template.is_draft = data.is_draft
    template.is_active = data.is_active
    template.matching_rules = matching
    template.processing_config = processing
    template.metadata_config = metadata
    template.output_config = output
    await repo.update(template)
    return template


async def _validate_import_item(
    session: AsyncSession,
    user_id: str,
    index: int,
    item: TemplateBundleImportItem,
    *,
    existing_by_id: dict[int, RecordingTemplateModel],
    existing_by_name: dict[str, RecordingTemplateModel],
    names_in_bundle: dict[str, int],
) -> tuple[list[TemplateImportErrorItem], list[TemplateImportWarningItem]]:
    errors: list[TemplateImportErrorItem] = []
    warnings: list[TemplateImportWarningItem] = []

    if item.name in names_in_bundle and names_in_bundle[item.name] != index:
        errors.append(
            TemplateImportErrorItem(
                index=index,
                name=item.name,
                msg=f"Duplicate template name '{item.name}' in bundle",
            )
        )

    target: RecordingTemplateModel | None = None
    if item.id is not None:
        target = existing_by_id.get(item.id)
        if not target:
            errors.append(
                TemplateImportErrorItem(
                    index=index,
                    name=item.name,
                    msg=f"Template id {item.id} not found",
                )
            )
    else:
        other = existing_by_name.get(item.name)
        if other:
            errors.append(
                TemplateImportErrorItem(
                    index=index,
                    name=item.name,
                    msg=f"Template with name '{item.name}' already exists (id={other.id})",
                )
            )

    is_default = target.is_default if target else False
    try:
        validate_template_state(
            is_default=is_default,
            matching_rules=item.matching_rules,
            processing_config=item.processing_config,
            metadata_config=item.metadata_config,
            output_config=item.output_config,
        )
    except ValueError as exc:
        errors.append(TemplateImportErrorItem(index=index, name=item.name, msg=str(exc)))

    if is_default and (item.is_active is False or item.is_draft is True):
        errors.append(
            TemplateImportErrorItem(
                index=index,
                name=item.name,
                msg="Cannot deactivate or draft the default (base) template",
            )
        )

    for code, msg in collect_template_warnings(
        item.matching_rules,
        is_draft=item.is_draft,
        is_default=is_default,
    ):
        warnings.append(TemplateImportWarningItem(index=index, code=code, msg=msg))

    output_dump = item.output_config.model_dump(exclude_none=True) if item.output_config else None
    try:
        await validate_effective_output_config(session, user_id, output_dump or {})
    except InvalidOutputPresetsError as exc:
        errors.append(TemplateImportErrorItem(index=index, name=item.name, msg=str(exc)))

    return errors, warnings


async def import_templates_bundle(
    session: AsyncSession,
    user_id: str,
    raw: dict[str, Any],
    *,
    dry_run: bool,
) -> TemplateImportResult:
    try:
        normalized = normalize_raw_to_bundle_dict(raw)
        bundle = TemplateBundleImport.model_validate(normalized)
    except ValidationError as exc:
        return TemplateImportResult(
            ok=False,
            dry_run=dry_run,
            errors=[
                TemplateImportErrorItem(index=-1, name=None, loc=list(err["loc"]), msg=err["msg"])
                for err in exc.errors()
            ],
        )
    except TemplateBundleError as exc:
        return TemplateImportResult(
            ok=False,
            dry_run=dry_run,
            errors=[TemplateImportErrorItem(index=-1, name=None, msg=str(exc))],
        )

    repo = RecordingTemplateRepository(session)
    all_templates = await repo.find_by_user(user_id, include_drafts=True)
    existing_by_id = {t.id: t for t in all_templates}
    existing_by_name = {t.name: t for t in all_templates}

    names_in_bundle: dict[str, int] = {}
    for idx, item in enumerate(bundle.templates):
        names_in_bundle[item.name] = idx

    all_errors: list[TemplateImportErrorItem] = []
    all_warnings: list[TemplateImportWarningItem] = []
    for idx, item in enumerate(bundle.templates):
        errs, warns = await _validate_import_item(
            session,
            user_id,
            idx,
            item,
            existing_by_id=existing_by_id,
            existing_by_name=existing_by_name,
            names_in_bundle=names_in_bundle,
        )
        all_errors.extend(errs)
        all_warnings.extend(warns)

    new_count = sum(1 for item in bundle.templates if item.id is None)
    if new_count:
        quotas = await QuotaService(session).get_effective_quotas(user_id)
        max_templates = quotas.get("max_templates")
        if max_templates is not None:
            current = await repo.count_matchable_by_user(user_id)
            if current + new_count > max_templates:
                all_errors.append(
                    TemplateImportErrorItem(
                        index=-1,
                        name=None,
                        msg=f"Templates limit exceeded: would create {new_count}, limit {max_templates}, current {current}",
                    )
                )

    if all_errors:
        return TemplateImportResult(ok=False, dry_run=dry_run, errors=all_errors, warnings=all_warnings)

    if dry_run:
        created_preview = [
            TemplateImportResultItem(id=0, name=item.name) for item in bundle.templates if item.id is None
        ]
        updated_preview = [
            TemplateImportResultItem(id=item.id or 0, name=item.name)
            for item in bundle.templates
            if item.id is not None
        ]
        return TemplateImportResult(
            ok=True,
            dry_run=True,
            created=created_preview,
            updated=updated_preview,
            warnings=all_warnings,
        )

    created: list[TemplateImportResultItem] = []
    updated: list[TemplateImportResultItem] = []
    for item in bundle.templates:
        matching, processing, metadata, output = _config_dump(item)
        if item.id is None:
            row = await repo.create(
                user_id=user_id,
                name=item.name,
                description=item.description,
                matching_rules=matching,
                processing_config=processing,
                metadata_config=metadata,
                output_config=output,
                is_draft=item.is_draft,
            )
            row.is_active = item.is_active
            await repo.update(row)
            created.append(TemplateImportResultItem(id=row.id, name=row.name))
            existing_by_id[row.id] = row
            existing_by_name[row.name] = row
        else:
            replace = RecordingTemplateReplace(
                name=item.name,
                description=item.description,
                is_draft=item.is_draft,
                is_active=item.is_active,
                matching_rules=item.matching_rules,
                processing_config=item.processing_config,
                metadata_config=item.metadata_config,
                output_config=item.output_config,
            )
            row = await replace_template(session, user_id, item.id, replace)
            updated.append(TemplateImportResultItem(id=row.id, name=row.name))

    return TemplateImportResult(
        ok=True,
        dry_run=False,
        created=created,
        updated=updated,
        warnings=all_warnings,
    )
