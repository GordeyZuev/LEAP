"""Processing preferences schemas"""

from pydantic import BaseModel, ConfigDict, Field

from api.shared.enums import Granularity


class ProcessingPreferences(BaseModel):
    """Settings of processing of recording."""

    enable_transcription: bool = Field(True, description="Enable transcription")
    enable_subtitles: bool = Field(True, description="Enable generation of subtitles")
    enable_topics: bool = Field(True, description="Enable extraction of topics")
    granularity: Granularity = Field(Granularity.LONG, description="Level of detail: short, medium, or long")
    transcription_model: str = Field(
        "universal-2",
        description="AssemblyAI speech model (universal-2, universal-3-pro). Metadata only — actual model set via ASSEMBLYAI_SPEECH_MODELS env.",
    )
    topic_model: str = Field("deepseek", description="Model for extraction of topics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enable_transcription": True,
                "enable_subtitles": True,
                "enable_topics": True,
                "granularity": Granularity.LONG,
                "transcription_model": "universal-2",
                "topic_model": "deepseek",
            }
        }
    )
