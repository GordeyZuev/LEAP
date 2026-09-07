"""Companion files stored next to the source video (chat, session materials)."""

from pydantic import BaseModel, Field


class SourceExtraFile(BaseModel):
    """One companion file stored next to the source video."""

    name: str = Field(..., description="Original file name, used for the download")
    extension: str = Field(..., description="Lowercase extension, for the UI badge")
    size: int | None = Field(None, description="Size in bytes when the manifest recorded it")
    url: str = Field(..., description="Time-limited download URL")


class SourceExtrasResponse(BaseModel):
    """Companion files fetched from the source alongside the video.

    Produced by MTS Link ingestion: the session chat log and materials uploaded to the
    event. Empty for sources that have no such artifacts.
    """

    chat: SourceExtraFile | None = Field(None, description="Session chat log, when saved")
    files: list[SourceExtraFile] = Field(default_factory=list, description="Session materials (slides, PDFs)")
    expires_in: int = Field(..., description="Lifetime of the returned URLs, seconds")
