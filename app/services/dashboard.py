from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Lead, LeadStatus, User
from app.models.auth import UserPublic
from app.models.dashboard import DashboardMetricas, DashboardResumenResponse


def _to_public_user(user: User) -> UserPublic:
    return UserPublic(
        user_id=user.id,
        nombre_completo=user.full_name,
        email=user.email,
        activo=user.is_active,
        creado_en=user.created_at,
    )


def get_dashboard_summary(db: Session, current_user: User) -> DashboardResumenResponse:
    total_usuarios = db.scalar(select(func.count(User.id))) or 0
    total_leads = db.scalar(select(func.count(Lead.id))) or 0
    leads_confirmados = db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.confirmed)) or 0
    leads_pendientes = db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.pending)) or 0

    return DashboardResumenResponse(
        mensaje="Dashboard cargado correctamente.",
        generado_en=datetime.now(timezone.utc),
        usuario=_to_public_user(current_user),
        metricas=DashboardMetricas(
            total_usuarios=total_usuarios,
            total_leads=total_leads,
            leads_confirmados=leads_confirmados,
            leads_pendientes=leads_pendientes,
        ),
        sugerencias=[
            "Completa tu perfil de sueño para mejorar recomendaciones.",
            "Conecta tu oxímetro para enriquecer el análisis nocturno.",
            "Configura tu rutina de descanso para recibir alertas personalizadas.",
        ],
    )
