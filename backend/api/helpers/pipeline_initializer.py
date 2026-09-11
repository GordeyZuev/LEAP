"""Pipeline initialization from configuration (output targets)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import OutputTargetModel, RecordingModel
from database.template_models import OutputPresetModel
from models.recording import TargetStatus, TargetType


async def ensure_output_targets(
    session: AsyncSession,
    recording: RecordingModel,
    output_config: dict[str, Any],
    *,
    include_copy: bool = True,
) -> list[OutputTargetModel]:
    """Ensure output_targets exist (create only missing ones).

    LEAP targets are always created when an active leap preset is listed.
    Copy platforms (YouTube / Yandex Disk) are created when ``include_copy`` is true.
    """
    existing_target_types = {
        t.value if isinstance(t, TargetType) else str(t) for t in (target.target_type for target in recording.outputs)
    }
    preset_ids = output_config.get("preset_ids", [])
    publish_leap = output_config.get("publish_leap", True)

    if not preset_ids:
        return list(recording.outputs)

    query = select(OutputPresetModel).where(
        OutputPresetModel.id.in_(preset_ids),
        OutputPresetModel.user_id == recording.user_id,
        OutputPresetModel.is_active,
    )
    result = await session.execute(query)
    presets = result.scalars().all()

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

    if new_targets:
        await session.flush()

    return list(recording.outputs) + new_targets
