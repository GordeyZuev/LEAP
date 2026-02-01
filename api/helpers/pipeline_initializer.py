"""Helper for automatic pipeline initialization from configuration.

Creates processing_stages and output_targets based on:
- RecordingTemplate.processing_config
- RecordingTemplate.output_config
- User config (unified_config)
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import OutputTargetModel, ProcessingStageModel, RecordingModel
from models.recording import ProcessingStageStatus, ProcessingStageType, TargetStatus, TargetType


async def initialize_processing_stages_from_config(
    session: AsyncSession,
    recording: RecordingModel,
    processing_config: dict[str, Any],
) -> list[ProcessingStageModel]:
    """
    Create processing_stages based on configuration.

    Args:
        session: DB session
        recording: Recording model
        processing_config: Processing config from template/user_config

    Returns:
        List of created ProcessingStageModel

    Example processing_config:
        {
            "trimming": {
                "enable_trimming": True,
                "silence_threshold": -40.0,
                ...
            },
            "transcription": {
                "enable_transcription": True,
                "provider": "fireworks",
                "enable_topics": True,
                "enable_subtitles": True,
                ...
            }
        }
    """
    stages_to_create = []

    # Check trimming settings
    trimming_config = processing_config.get("trimming", {})
    if trimming_config.get("enable_trimming", True):
        stages_to_create.append(
            ProcessingStageModel(
                recording_id=recording.id,
                user_id=recording.user_id,
                stage_type=ProcessingStageType.TRIM,
                status=ProcessingStageStatus.PENDING,
                stage_meta={
                    "silence_threshold": trimming_config.get("silence_threshold", -40.0),
                    "min_silence_duration": trimming_config.get("min_silence_duration", 2.0),
                },
            )
        )

    # Check transcription settings
    transcription_config = processing_config.get("transcription", {})

    if transcription_config.get("enable_transcription", False):
        stages_to_create.append(
            ProcessingStageModel(
                recording_id=recording.id,
                user_id=recording.user_id,
                stage_type=ProcessingStageType.TRANSCRIBE,
                status=ProcessingStageStatus.PENDING,
                stage_meta={"provider": "fireworks"},
            )
        )

        if transcription_config.get("enable_topics", False):
            stages_to_create.append(
                ProcessingStageModel(
                    recording_id=recording.id,
                    user_id=recording.user_id,
                    stage_type=ProcessingStageType.EXTRACT_TOPICS,
                    status=ProcessingStageStatus.PENDING,
                    stage_meta={"mode": transcription_config.get("granularity", "long")},
                )
            )

        if transcription_config.get("enable_subtitles", False):
            stages_to_create.append(
                ProcessingStageModel(
                    recording_id=recording.id,
                    user_id=recording.user_id,
                    stage_type=ProcessingStageType.GENERATE_SUBTITLES,
                    status=ProcessingStageStatus.PENDING,
                    stage_meta={},
                )
            )

    for stage in stages_to_create:
        session.add(stage)

    await session.flush()

    return stages_to_create


async def initialize_output_targets_from_config(
    session: AsyncSession,
    recording: RecordingModel,
    output_config: dict[str, Any],
) -> list[OutputTargetModel]:
    """
    Создать output_targets на основе конфигурации.

    Args:
        session: DB session
        recording: Recording model
        output_config: Конфигурация выгрузки из template

    Returns:
        Список созданных OutputTargetModel

    Example output_config:
        {
            "preset_ids": [1, 2, 3]
        }
    """
    from sqlalchemy import select

    from database.template_models import OutputPresetModel

    targets_to_create = []

    preset_ids = output_config.get("preset_ids", [])

    if not preset_ids:
        return []

    # Загружаем все presets из БД одним запросом
    query = select(OutputPresetModel).where(
        OutputPresetModel.id.in_(preset_ids),
        OutputPresetModel.user_id == recording.user_id,
        OutputPresetModel.is_active,
    )
    result = await session.execute(query)
    presets = result.scalars().all()

    # Создаем target для каждого preset
    for preset in presets:
        # Берем платформу из preset (single source of truth)
        try:
            target_type = TargetType[preset.platform.upper()]
        except KeyError:
            # Если платформа не найдена, пропускаем
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

    # Добавляем targets в сессию
    for target in targets_to_create:
        session.add(target)

    # Flush чтобы получить ID
    await session.flush()

    return targets_to_create


async def ensure_processing_stages(
    session: AsyncSession,
    recording: RecordingModel,
    processing_config: dict[str, Any],
) -> list[ProcessingStageModel]:
    """
    Ensure processing_stages exist (create only missing ones).

    Args:
        session: DB session
        recording: Recording model
        processing_config: Processing configuration

    Returns:
        List of all processing_stages (existing + created)
    """
    existing_stage_types = {stage.stage_type for stage in recording.processing_stages}

    required_stages = []

    # Check trimming settings
    trimming_config = processing_config.get("trimming", {})
    if trimming_config.get("enable_trimming", True):
        required_stages.append(
            (
                ProcessingStageType.TRIM,
                {
                    "silence_threshold": trimming_config.get("silence_threshold", -40.0),
                    "min_silence_duration": trimming_config.get("min_silence_duration", 2.0),
                },
            )
        )

    # Check transcription settings
    transcription_config = processing_config.get("transcription", {})

    if transcription_config.get("enable_transcription", False):
        required_stages.append(
            (
                ProcessingStageType.TRANSCRIBE,
                {"provider": "fireworks"},
            )
        )

        if transcription_config.get("enable_topics", False):
            required_stages.append(
                (
                    ProcessingStageType.EXTRACT_TOPICS,
                    {"mode": transcription_config.get("granularity", "long")},
                )
            )

        if transcription_config.get("enable_subtitles", False):
            required_stages.append((ProcessingStageType.GENERATE_SUBTITLES, {}))

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
    """
    Убедиться, что output_targets существуют (создать только отсутствующие).

    Args:
        session: DB session
        recording: Recording model
        output_config: Конфигурация выгрузки

    Returns:
        Список всех output_targets (существующие + созданные)
    """
    from sqlalchemy import select

    from database.template_models import OutputPresetModel

    existing_target_types = {target.target_type for target in recording.outputs}

    preset_ids = output_config.get("preset_ids", [])
    new_targets = []

    if not preset_ids:
        return list(recording.outputs)

    # Загружаем все presets из БД одним запросом
    query = select(OutputPresetModel).where(
        OutputPresetModel.id.in_(preset_ids),
        OutputPresetModel.user_id == recording.user_id,
        OutputPresetModel.is_active,
    )
    result = await session.execute(query)
    presets = result.scalars().all()

    for preset in presets:
        try:
            target_type = TargetType[preset.platform.upper()]
        except KeyError:
            continue

        # Проверяем, существует ли уже target
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
