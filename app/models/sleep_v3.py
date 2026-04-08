from pydantic import BaseModel


class SleepV3Detail(BaseModel):
    prob_audio: float
    prob_spo2: float
    spo2_drop_pts: float
    peso_audio: float
    peso_spo2: float


class SleepV3PredictResponse(BaseModel):
    nivel: str
    interpretacion: str
    probabilidad: float
    detalle: SleepV3Detail
    modo: str
    perfil: str
    version: str


class SleepV3HealthResponse(BaseModel):
    status: str
    version: str | None = None
    modelo: dict | None = None
    modos_disponibles: list[str]


class SleepV3ModosResponse(BaseModel):
    modos: dict
