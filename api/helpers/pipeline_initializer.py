"""Pipeline initialization from configuration (stages and output targets)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import OutputTargetModel, ProcessingStageModel, RecordingModel
from database.template_models import OutputPresetModel
from models.recording import ProcessingStageStatus, ProcessingStageType, TargetStatus, TargetType


def _build_stages_from_config(
    recording: RecordingModel, processing_config: dict[str, Any]
) -> list[tuple[ProcessingStageType, dict]]:
    """Build list of required stages from processing config."""
    stages = []
    trimming_config = processing_config.get("trimming", {})

    if trimming_config.get("enable_trimming", True):
        stages.append(
            (
                ProcessingStageType.TRIM,
                {
                    "silence_threshold": trimming_config.get("silence_threshold", -40.0),
                    "min_silence_duration": trimming_config.get("min_silence_duration", 2.0),
                },
            )
        )

    transcription_config = processing_config.get("transcription", {})
    if transcription_config.get("enable_transcription", False):
        stages.append((ProcessingStageType.TRANSCRIBE, {"provider": "fireworks"}))

        if transcription_config.get("enable_topics", False):
            stages.append(
                (ProcessingStageType.EXTRACT_TOPICS, {"mode": transcription_config.get("granularity", "long")})
            )

        if transcription_config.get("enable_subtitles", False):
            stages.append((ProcessingStageType.GENERATE_SUBTITLES, {}))

    return stages


async def initialize_processing_stages_from_config(
    session: AsyncSession,
    recording: RecordingModel,
    processing_config: dict[str, Any],
) -> list[ProcessingStageModel]:
    """Create processing_stages based on configuration."""
    stages_to_create = [
        ProcessingStageModel(
            recording_id=recording.id,
            user_id=recording.user_id,
            stage_type=stage_type,
            status=ProcessingStageStatus.PENDING,
            stage_meta=meta,
        )
        for stage_type, meta in _build_stages_from_config(recording, processing_config)
    ]

    for stage in stages_to_create:
        session.add(stage)

    await session.flush()
    return stages_to_create


async def initialize_output_targets_from_config(
    session: AsyncSession,
    recording: RecordingModel,
    output_config: dict[str, Any],
) -> list[OutputTargetModel]:
    """Create output_targets based on configuration."""
    preset_ids = output_config.get("preset_ids", [])
    if not preset_ids:
        return []

    query = select(OutputPresetModel).where(
        OutputPresetModel.id.in_(preset_ids),
        OutputPresetModel.user_id == recording.user_id,
        OutputPresetModel.is_active,
    )
    result = await session.execute(query)
    presets = result.scalars().all()

    targets_to_create = []
    for preset in presets:
        try:
            target_type = TargetType[preset.platform.upper()]
        except KeyError:
            continue

        targets_to_create.append(
            OutputTargetModel(
                recording_id=recording.id,
                user_id=recording.user_id,
                preset_id=preset.id,
                target_type=target_type,
                status=TargetStatus.NOT_UPLOADED,
                target_meta={},
            )
        )

    for target in targets_to_create:
        session.add(target)

    await session.flush()
    return targets_to_create


async def ensure_processing_stages(
    session: AsyncSession,
    recording: RecordingModel,
    processing_config: dict[str, Any],
) -> list[ProcessingStageModel]:
    """Ensure processing_stages exist (create only missing ones)."""
    existing_stage_types = {stage.stage_type for stage in recording.processing_stages}
    required_stages = _build_stages_from_config(recording, processing_config)

    new_stages = []
    for stage_type, meta in required_stages:
        if stage_type not in existing_stage_types:
            new_stage = ProcessingStageModel(
                recording_id=recording.id,
                user_id=recording.user_id,
                stage_type=stage_type,
                status=ProcessingStageStatus.PENDING,
                stage_meta=meta,
            )
            session.add(new_stage)
            new_stages.append(new_stage)

    if new_stages:
        await session.flush()

    return list(recording.processing_stages) + new_stages


async def ensure_output_targets(
    session: AsyncSession,
    recording: RecordingModel,
    output_config: dict[str, Any],
) -> list[OutputTargetModel]:
    """Ensure output_targets exist (create only missing ones)."""
    existing_target_types = {target.target_type for target in recording.outputs}
    preset_ids = output_config.get("preset_ids", [])

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
