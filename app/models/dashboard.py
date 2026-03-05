from datetime import datetime

from pydantic import BaseModel

from app.models.auth import UserPublic


class DashboardMetricas(BaseModel):
    total_usuarios: int
    total_leads: int
    leads_confirmados: int
    leads_pendientes: int


class DashboardResumenResponse(BaseModel):
    ok: bool = True
    mensaje: str
    generado_en: datetime
    usuario: UserPublic
    metricas: DashboardMetricas
    sugerencias: list[str]
