from typing import Any

from pydantic import BaseModel, Field


class AudioMetadata(BaseModel):
    file_name: str = Field(..., description="Original audio filename.")
    duration_seconds: float = Field(..., gt=0, description="Audio duration in seconds.")
    sample_rate_hz: int = Field(..., gt=0, description="Sampling rate in Hz.")
    channels: int = Field(..., ge=1, le=2, description="Number of channels.")
    codec: str | None = Field(default=None, description="Audio codec, e.g. PCM or AAC.")
    patient_id: str | None = Field(default=None, description="Optional patient identifier.")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional metadata.")


class AnalyzeResponse(BaseModel):
    status: str
    quality_score: float = Field(..., ge=0, le=100)
    insights: list[str]
