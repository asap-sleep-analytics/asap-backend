from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SleepSession, User
from app.models.auth import UserPublic
from app.models.dashboard import DashboardEventosDetectados, DashboardIndicadores, DashboardResumenResponse
from app.models.sleep import SleepContinuityPoint


def _to_public_user(user: User) -> UserPublic:
    return UserPublic(
        user_id=user.id,
        nombre_completo=user.full_name,
        email=user.email,
        activo=user.is_active,
        ronca_habitualmente=user.ronca_habitualmente,
        cansancio_diurno=user.cansancio_diurno,
        creado_en=user.created_at,
    )


def _latest_session_for_user(db: Session, user_id: str) -> SleepSession | None:
    finished = db.scalar(
        select(SleepSession)
        .where(SleepSession.user_id == user_id, SleepSession.end_time.is_not(None))
        .order_by(SleepSession.end_time.desc())
        .limit(1)
    )
    if finished:
        return finished

    return db.scalar(
        select(SleepSession)
        .where(SleepSession.user_id == user_id)
        .order_by(SleepSession.start_time.desc())
        .limit(1)
    )


def get_dashboard_summary(db: Session, current_user: User) -> DashboardResumenResponse:
    latest_session = _latest_session_for_user(db, current_user.id)

    if not latest_session:
        return DashboardResumenResponse(
            mensaje="Aún no tienes sesiones nocturnas registradas.",
            generado_en=datetime.now(timezone.utc),
            usuario=_to_public_user(current_user),
            indicadores=DashboardIndicadores(
                sleep_score=0,
                eventos_apnea_ronquido=DashboardEventosDetectados(ronquidos=0, apnea=0, total=0),
                continuidad=[],
            ),
            sugerencias=[
                "Realiza tu primera sesión nocturna para ver métricas de sueño.",
                "Ejecuta calibración de micrófono antes de iniciar monitoreo.",
                "Recuerda: esta herramienta es de bienestar y seguimiento personal.",
            ],
            disclaimer_medico="A.S.A.P. es una herramienta de bienestar, no reemplaza un diagnóstico clínico profesional.",
        )

    continuity = [SleepContinuityPoint(**point) for point in (latest_session.continuity_timeline or [])]
    ronquidos = latest_session.snore_count or 0
    apnea = latest_session.apnea_events or 0
    total_eventos = ronquidos + apnea
    score = latest_session.sleep_score or 0

    return DashboardResumenResponse(
        mensaje="Dashboard cargado correctamente.",
        generado_en=datetime.now(timezone.utc),
        usuario=_to_public_user(current_user),
        indicadores=DashboardIndicadores(
            sleep_score=score,
            eventos_apnea_ronquido=DashboardEventosDetectados(
                ronquidos=ronquidos,
                apnea=apnea,
                total=total_eventos,
            ),
            continuidad=continuity,
        ),
        sugerencias=[
            "Si tu score cae por debajo de 70 durante 3 días, revisa hábitos de descanso.",
            "Si hay muchos eventos de apnea/ronquido, considera consultar un profesional.",
            "Mantén el teléfono estable y calibrado para mejorar calidad de medición.",
        ],
        disclaimer_medico="A.S.A.P. es una herramienta de bienestar, no reemplaza un diagnóstico clínico profesional.",
    )
