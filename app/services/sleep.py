from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SleepSession, User
from app.models.sleep import (
    SleepCalibrationResponse,
    SleepContinuityPoint,
    SleepSessionFinishRequest,
    SleepSessionRecord,
    SleepSessionStartRequest,
)


def _to_record(session: SleepSession) -> SleepSessionRecord:
    timeline_raw = session.continuity_timeline or []
    timeline = [SleepContinuityPoint(**item) for item in timeline_raw]
    return SleepSessionRecord(
        session_id=session.id,
        user_id=session.user_id,
        start_time=session.start_time,
        end_time=session.end_time,
        snore_count=session.snore_count,
        apnea_events=session.apnea_events,
        avg_oxygen=session.avg_oxygen,
        ambient_noise_level=session.ambient_noise_level,
        sleep_score=session.sleep_score,
        continuidad=timeline,
        created_at=session.created_at,
    )


def evaluate_noise_level(ambient_noise_level: float) -> SleepCalibrationResponse:
    if ambient_noise_level <= 35:
        return SleepCalibrationResponse(
            mensaje="Calibración completada. El entorno es óptimo para monitoreo.",
            nivel_ruido="optimo",
            recomendacion="Puedes iniciar monitoreo sin ajustes.",
        )

    if ambient_noise_level <= 50:
        return SleepCalibrationResponse(
            mensaje="Calibración completada. Hay ruido moderado.",
            nivel_ruido="moderado",
            recomendacion="Procura alejar el teléfono de fuentes de ruido continuo.",
        )

    return SleepCalibrationResponse(
        mensaje="Calibración completada. Ruido alto detectado.",
        nivel_ruido="alto",
        recomendacion="Reduce ruido ambiente antes de iniciar para evitar falsos positivos.",
    )


def _compute_sleep_score(
    start_time: datetime,
    end_time: datetime,
    snore_count: int,
    apnea_events: int,
    avg_oxygen: float | None,
    ambient_noise_level: float | None,
) -> int:
    duration_hours = max((end_time - start_time).total_seconds() / 3600, 0)

    score = 100.0

    if duration_hours < 6:
        score -= min((6 - duration_hours) * 8, 30)
    elif duration_hours > 9:
        score -= min((duration_hours - 9) * 3, 10)

    score -= min(snore_count * 0.15, 20)
    score -= min(apnea_events * 2.8, 40)

    if avg_oxygen is not None and avg_oxygen < 94:
        score -= min((94 - avg_oxygen) * 2.2, 18)

    if ambient_noise_level is not None and ambient_noise_level > 45:
        score -= min((ambient_noise_level - 45) * 0.8, 15)

    return int(max(0, min(100, round(score))))


def _build_continuity_timeline(
    start_time: datetime,
    end_time: datetime,
    snore_count: int,
    apnea_events: int,
) -> list[dict]:
    duration_minutes = max(int((end_time - start_time).total_seconds() // 60), 10)
    points = max(6, min(60, duration_minutes // 10))

    event_density = (apnea_events * 2 + snore_count / 20) / max(duration_minutes / 60, 1)
    threshold = max(10, min(75, int(event_density * 10) + 15))

    timeline: list[dict] = []
    for index in range(points):
        probe = (index * 17 + snore_count + apnea_events * 3) % 100
        state = "interrupcion" if probe < threshold else "deep_sleep"
        timeline.append({
            "minuto": index * 10,
            "estado": state,
        })

    return timeline


def start_sleep_session(db: Session, user: User, payload: SleepSessionStartRequest) -> SleepSessionRecord:
    start_time = payload.start_time or datetime.now(timezone.utc)

    session = SleepSession(
        user_id=user.id,
        start_time=start_time,
        ambient_noise_level=payload.ambient_noise_level,
        snore_count=0,
        apnea_events=0,
        continuity_timeline=[],
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return _to_record(session)


def finish_sleep_session(
    db: Session,
    user: User,
    session_id: str,
    payload: SleepSessionFinishRequest,
) -> SleepSessionRecord:
    session = db.scalar(select(SleepSession).where(SleepSession.id == session_id, SleepSession.user_id == user.id))
    if not session:
        raise ValueError("Sesión no encontrada.")

    if session.end_time is not None:
        raise ValueError("La sesión ya fue finalizada.")

    end_time = payload.end_time or datetime.now(timezone.utc)
    start_time = session.start_time

    # SQLite suele devolver datetime naive; normalizamos para comparar sin errores.
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    if end_time <= start_time:
        raise ValueError("La hora final debe ser posterior a la hora de inicio.")

    session.end_time = end_time
    session.snore_count = payload.snore_count
    session.apnea_events = payload.apnea_events
    session.avg_oxygen = payload.avg_oxygen
    if payload.ambient_noise_level is not None:
        session.ambient_noise_level = payload.ambient_noise_level

    session.sleep_score = _compute_sleep_score(
        start_time=start_time,
        end_time=end_time,
        snore_count=session.snore_count,
        apnea_events=session.apnea_events,
        avg_oxygen=session.avg_oxygen,
        ambient_noise_level=session.ambient_noise_level,
    )

    session.continuity_timeline = _build_continuity_timeline(
        start_time=start_time,
        end_time=end_time,
        snore_count=session.snore_count,
        apnea_events=session.apnea_events,
    )

    db.commit()
    db.refresh(session)

    return _to_record(session)


def list_sleep_sessions(db: Session, user: User, limit: int = 20) -> list[SleepSessionRecord]:
    rows = db.scalars(
        select(SleepSession)
        .where(SleepSession.user_id == user.id)
        .order_by(SleepSession.start_time.desc())
        .limit(limit)
    ).all()
    return [_to_record(item) for item in rows]
