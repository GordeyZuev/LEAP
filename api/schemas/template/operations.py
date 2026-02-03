"""Schemas for template operations endpoints."""

from pydantic import BaseModel

from api.schemas.common import BASE_MODEL_CONFIG


class BulkDeleteResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    template_id: int
    template_name: str
    deleted_recordings: int
    deleted_targets: int


class TemplateStatsResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    template_id: int
    template_name: str
    total_recordings: int
    by_status: dict
    last_matched_at: str | None = None
    is_active: bool


class TemplatePreviewRecording(BaseModel):
    model_config = BASE_MODEL_CONFIG

    id: int
    display_name: str
    current_status: str
    current_is_mapped: bool
    will_become_status: str
    will_become_is_mapped: bool
    start_time: str
    duration: int | None = None
    input_source_id: int | None = None


class TemplatePreviewResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    template_id: int
    template_name: str
    mode: str
    total_checked: int
    will_match_count: int
    will_match: list[TemplatePreviewRecording]
    note: str


class RematchTaskResponse(BaseModel):
    model_config = BASE_MODEL_CONFIG

    message: str
    task_id: str
    template_id: int
    template_name: str
    only_unmapped: bool
    note: str
