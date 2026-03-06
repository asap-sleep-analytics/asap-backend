from datetime import datetime

from pydantic import BaseModel

from app.models.auth import UserPublic
from app.models.sleep import SleepContinuityPoint


class DashboardEventosDetectados(BaseModel):
    ronquidos: int
    apnea: int
    total: int


class DashboardIndicadores(BaseModel):
    sleep_score: int
    eventos_apnea_ronquido: DashboardEventosDetectados
    continuidad: list[SleepContinuityPoint]


class DashboardResumenResponse(BaseModel):
    ok: bool = True
    mensaje: str
    generado_en: datetime
    usuario: UserPublic
    indicadores: DashboardIndicadores
    sugerencias: list[str]
    disclaimer_medico: str
    premium_disponible: bool = False
    premium_etiqueta: str = "Coming Soon"
