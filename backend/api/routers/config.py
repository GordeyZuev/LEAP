"""Config resolution API for UI preload."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.dependencies import get_db_session
from api.repositories.recording_repos import RecordingRepository
from api.schemas.auth import UserInDB
from api.schemas.common import BASE_MODEL_CONFIG
from api.services.config_resolver import ConfigLayer, ConfigResolver, ResolveContext

router = APIRouter(prefix="/api/v1/config", tags=["Config"])


class ConfigLayerResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    source: str
    config: dict[str, Any] = Field(default_factory=dict)
    id: int | None = None
    name: str | None = None


class ResolvedConfigResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    processing_config: dict[str, Any] = Field(default_factory=dict)
    metadata_config: dict[str, Any] = Field(default_factory=dict)
    output_config: dict[str, Any] = Field(default_factory=dict)
    layers: list[ConfigLayerResponse] | None = None


def _layer_to_response(layer: ConfigLayer) -> ConfigLayerResponse:
    return ConfigLayerResponse(source=layer.source, config=layer.config, id=layer.id, name=layer.name)


@router.get("/resolve", response_model=ResolvedConfigResponse)
async def resolve_config(
    recording_id: int | None = Query(None, description="Recording to resolve overrides for"),
    template_id: int | None = Query(None, description="Preview named template atop default"),
    include_layers: bool = Query(False, description="Include merge layers for UI preload"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResolvedConfigResponse:
    """Resolve effective configuration with optional layer breakdown."""
    recording = None
    if recording_id is not None:
        recording = await RecordingRepository(session).get_by_id(recording_id, current_user.id)
        if not recording:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recording {recording_id} not found")

    resolver = ConfigResolver(session)
    try:
        resolved = await resolver.resolve(
            ResolveContext(
                user_id=current_user.id,
                recording=recording,
                preview_template_id=template_id,
                include_layers=include_layers,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    processing = resolved.processing
    nested_processing: dict[str, Any] = {}
    if "transcription" in processing:
        nested_processing["transcription"] = processing["transcription"]
    if "trimming" in processing:
        nested_processing["trimming"] = processing["trimming"]
    if "transcription_vocabulary" in processing:
        nested_processing["transcription_vocabulary"] = processing["transcription_vocabulary"]

    layers = [_layer_to_response(layer) for layer in resolved.layers] if include_layers else None

    return ResolvedConfigResponse(
        processing_config=nested_processing or processing,
        metadata_config=resolved.metadata,
        output_config=resolved.output,
        layers=layers,
    )
