"""Processing preferences schemas"""

from pydantic import BaseModel, ConfigDict, Field


class ProcessingPreferences(BaseModel):
    """Settings of processing of recording."""

    enable_transcription: bool = Field(True, description="Enable transcription")
    enable_subtitles: bool = Field(True, description="Enable generation of subtitles")
    enable_topics: bool = Field(True, description="Enable extraction of topics")
    granularity: str = Field("long", description="Level of detail of topic extraction (short/long)")
    transcription_model: str = Field("fireworks", description="Model for transcription")
    topic_model: str = Field("deepseek", description="Model for extraction of topics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enable_transcription": True,
                "enable_subtitles": True,
                "enable_topics": True,
                "granularity": "long",
                "transcription_model": "fireworks",
                "topic_model": "deepseek",
            }
        }
    )
