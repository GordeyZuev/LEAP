"""Pipeline initialization from configuration (output targets)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.leap_publish import (
    active_leap_from_presets,
    leap_meta_from_preset,
    merge_leap_metadata,
    should_enqueue_leap_publish,
)
from database.models import OutputTargetModel, RecordingModel
from database.template_models import OutputPresetModel
from models.recording import TargetStatus, TargetType


async def ensure_output_targets(
    session: AsyncSession,
    recording: RecordingModel,
    output_config: dict[str, Any],
    *,
    include_copy: bool = True,
    metadata_config: dict[str, Any] | None = None,
) -> list[OutputTargetModel]:
    """Ensure output_targets exist (create only missing ones).

    LEAP targets are created when publish is configured (look preset, playlists, or share).
    Copy platforms (YouTube / Yandex Disk) are created when ``include_copy`` is true.
    """
    existing_target_types = {
        t.value if isinstance(t, TargetType) else str(t) for t in (target.target_type for target in recording.outputs)
    }
    preset_ids = output_config.get("preset_ids") or []
    publish_leap = output_config.get("publish_leap", True)

    presets: list[OutputPresetModel] = []
    if preset_ids:
        query = select(OutputPresetModel).where(
            OutputPresetModel.id.in_(preset_ids),
            OutputPresetModel.user_id == recording.user_id,
            OutputPresetModel.is_active,
        )
        result = await session.execute(query)
        presets = list(result.scalars().all())

    leap_preset = active_leap_from_presets(presets) if presets else None
    leap_meta = merge_leap_metadata(
        leap_meta_from_preset(leap_preset) if leap_preset else None,
        metadata_config=metadata_config,
    )
    need_leap = should_enqueue_leap_publish(
        output_config,
        leap_meta,
        has_leap_look_preset=leap_preset is not None,
    )

    if not preset_ids and not need_leap:
        return list(recording.outputs)

    new_targets = []
    for preset in presets:
        try:
            target_type = TargetType[preset.platform.upper()]
        except KeyError:
            continue

        if target_type == TargetType.LEAP:
            if not publish_leap:
                continue
        elif not include_copy:
            continue

        if target_type.value not in existing_target_types:
            new_target = OutputTargetModel(
                recording_id=recording.id,
                user_id=recording.user_id,
                preset_id=preset.id,
                target_type=target_type,
                status=TargetStatus.NOT_UPLOADED,
                target_meta={},
            )
            session.add(new_target)
            new_targets.append(new_target)
            existing_target_types.add(target_type.value)

    if need_leap and publish_leap and TargetType.LEAP.value not in existing_target_types:
        new_target = OutputTargetModel(
            recording_id=recording.id,
            user_id=recording.user_id,
            preset_id=leap_preset.id if leap_preset else None,
            target_type=TargetType.LEAP,
            status=TargetStatus.NOT_UPLOADED,
            target_meta={},
        )
        session.add(new_target)
        new_targets.append(new_target)

    if new_targets:
        await session.flush()

    return list(recording.outputs) + new_targets
