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
