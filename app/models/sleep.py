from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SleepState = Literal["deep_sleep", "interrupcion"]


class SleepCalibrationRequest(BaseModel):
    ambient_noise_level: float = Field(..., ge=0, le=120, description="Ruido ambiente en decibeles (dB).")


class SleepCalibrationResponse(BaseModel):
    ok: bool = True
    mensaje: str
    nivel_ruido: str
    recomendacion: str


class SleepSessionStartRequest(BaseModel):
    start_time: datetime | None = None
    ambient_noise_level: float | None = Field(default=None, ge=0, le=120)


class SleepSessionFinishRequest(BaseModel):
    end_time: datetime | None = None
    snore_count: int = Field(default=0, ge=0)
    apnea_events: int = Field(default=0, ge=0)
    avg_oxygen: float | None = Field(default=None, ge=50, le=100)
    ambient_noise_level: float | None = Field(default=None, ge=0, le=120)


class SleepContinuityPoint(BaseModel):
    minuto: int
    estado: SleepState


class SleepSessionRecord(BaseModel):
    session_id: str
    user_id: str
    start_time: datetime
    end_time: datetime | None
    snore_count: int
    apnea_events: int
    avg_oxygen: float | None
    ambient_noise_level: float | None
    sleep_score: int | None
    continuidad: list[SleepContinuityPoint]
    created_at: datetime


class SleepSessionResponse(BaseModel):
    ok: bool = True
    mensaje: str
    sesion: SleepSessionRecord


class SleepFragmentRecord(BaseModel):
    session_id: str
    fragment_index: int
    filename: str
    bytes_size: int
    duration_seconds: float | None
    queued_fragments: int
    created_at: datetime


class SleepFragmentUploadResponse(BaseModel):
    ok: bool = True
    mensaje: str
    fragmento: SleepFragmentRecord


class SleepDetectionLogRecord(BaseModel):
    log_id: int
    session_id: str
    window_index: int
    start_second: float
    end_second: float
    label: str
    confidence_score: float
    model_source: str
    model_version: str | None
    created_at: datetime


class SleepFeedbackRequest(BaseModel):
    calificacion_descanso: int = Field(..., ge=1, le=5)
    desperto_cansado: bool | None = None
    comentario: str | None = Field(default=None, max_length=500)


class SleepFeedbackRecord(BaseModel):
    feedback_id: int
    session_id: str
    user_id: str
    calificacion_descanso: int
    desperto_cansado: bool | None
    comentario: str | None
    created_at: datetime
    updated_at: datetime


class SleepFeedbackResponse(BaseModel):
    ok: bool = True
    mensaje: str
    feedback: SleepFeedbackRecord
