"""Transcription and topic processing schemas"""

from pydantic import BaseModel, Field


class ExtractTopicsRequest(BaseModel):
    """Request for extraction of topics."""

    model: str = Field(
        default="deepseek",
        description="Model for extraction of topics: 'deepseek' or 'fireworks_deepseek'",
    )
    granularity: str = Field(
        default="long",
        description="Extraction mode: 'short' (large topics) or 'long' (detailed topics)",
    )
    version_id: str | None = Field(
        default=None,
        description="Version ID (if not specified, generated automatically)",
    )


class GenerateSubtitlesRequest(BaseModel):
    """Request for generation of subtitles."""

    formats: list[str] = Field(
        default=["srt", "vtt"],
        description="List of subtitle formats: 'srt', 'vtt'",
    )


class BatchTranscribeRequest(BaseModel):
    """Request for batch transcription."""

    recording_ids: list[int] = Field(..., description="List of recording IDs for transcription")
    granularity: str = Field(
        default="long",
        description="Extraction mode: 'short' or 'long'",
    )


class TopicTimestamp(BaseModel):
    """Topic with timestamps."""

    topic: str
    start: float
    end: float
    type: str | None = None  # "pause" for pauses


class TopicVersion(BaseModel):
    """Version of extraction of topics."""

    id: str
    model: str
    granularity: str
    created_at: str
    is_active: bool
    main_topics: list[str]
    topic_timestamps: list[TopicTimestamp]
    pauses: list[dict] | None = None


class TranscriptionStats(BaseModel):
    """Statistics of transcription."""

    words_count: int
    segments_count: int
    total_duration: float


class TranscriptionData(BaseModel):
    """Data about transcription."""

    exists: bool
    created_at: str | None = None
    language: str | None = None
    model: str | None = None
    stats: TranscriptionStats | None = None
    files: dict[str, str] | None = None


class TopicsData(BaseModel):
    """Data about topics."""

    exists: bool
    active_version: str | None = None
    versions: list[TopicVersion] | None = None


class VideoFileInfo(BaseModel):
    """Information about video file."""

    path: str | None = None
    size_mb: float | None = None
    exists: bool = False


class AudioFileInfo(BaseModel):
    """Information about audio file."""

    path: str | None = None
    size_mb: float | None = None
    exists: bool = False


class SubtitleFileInfo(BaseModel):
    """Information about subtitle file."""

    path: str | None = None
    exists: bool = False
    size_kb: float | None = None


class ThumbnailInfoExt(BaseModel):
    """Extended thumbnail information for recording details."""

    path: str | None = None
    exists: bool = False
    type: str | None = None  # "template" or "user"


class RecordingDetailsResponse(BaseModel):
    """Detailed information about recording."""

    id: int
    display_name: str
    status: str
    start_time: str
    duration: int | None = None

    # Video files
    videos: dict[str, VideoFileInfo] | None = None

    # Audio files
    audio: AudioFileInfo | None = None

    # Transcription
    transcription: TranscriptionData | None = None

    # Topics (all versions)
    topics: TopicsData | None = None

    # Subtitles
    subtitles: dict[str, SubtitleFileInfo] | None = None

    # Thumbnail
    thumbnail: ThumbnailInfoExt | None = None

    # Processing stages
    processing_stages: list[dict] | None = None

    # Upload to platforms
    uploads: dict[str, dict] | None = None


class ExtractTopicsResponse(BaseModel):
    """Response for extraction of topics."""

    success: bool
    task_id: str
    recording_id: int
    status: str
    message: str
    check_status_url: str


class GenerateSubtitlesResponse(BaseModel):
    """Response for generation of subtitles."""

    success: bool
    task_id: str
    recording_id: int
    status: str
    message: str
    check_status_url: str


class BatchTranscribeTaskInfo(BaseModel):
    """Information about batch transcription task."""

    recording_id: int
    status: str
    task_id: str | None = None
    error: str | None = None
    check_status_url: str | None = None


class BatchTranscribeResponse(BaseModel):
    """Response for batch transcription."""

    total: int
    queued: int
    errors: int
    tasks: list[BatchTranscribeTaskInfo]
