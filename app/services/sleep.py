import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    InvalidSessionTimeError,
    SessionAlreadyFinishedError,
    SessionNotFoundError,
)
from app.db.models import SleepDetectionLog, SleepSession, User, UserFeedback
from app.models.sleep import (
    LivePrediction,
    SleepCalibrationResponse,
    SleepContinuityPoint,
    SleepDetectionLogRecord,
    SleepFeedbackRecord,
    SleepFeedbackRequest,
    SleepFragmentRecord,
    SleepFragmentUploadResponse,
    SleepSessionFinishRequest,
    SleepSessionRecord,
    SleepSessionStartRequest,
)
from app.repositories.sleep_sessions import get_user_sleep_session
from app.services.audio_processor import build_session_audio_batch, cleanup_session_fragments
from app.services.ml_service import LABEL_APNEA, LABEL_NORMAL, LABEL_SNORE, SleepModel, WindowDetection

_FRAGMENT_ROOT = Path(settings.sleep_fragment_root)
_ALLOWED_AUDIO_EXTENSIONS = {".m4a", ".wav", ".aac", ".mp4", ".caf"}
_ALLOWED_AUDIO_MIME_TYPES = {
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/aac",
    "audio/x-caf",
    "audio/mpeg",
    "audio/x-mpeg",
    "audio/mp3",
}
_SCORE_PER_HOUR = 12.5
_APNEA_PENALTY_PER_EVENT = 8.0
_SNORE_PENALTY_PER_HOUR = 0.75
_sleep_model = SleepModel()


@dataclass(slots=True)
class SessionAnalysisSummary:
    snore_count: int
    apnea_events: int
    continuity_timeline: list[dict]
    ambient_noise_level: float | None
    detections: list[WindowDetection]
    model_source: str
    model_version: str


def _analysis_label(model_source: str | None, model_version: str | None) -> str | None:
    if model_source is None:
        return None
    if model_source == "sklearn":
        return "Análisis con modelo de sueño entrenado"
    if model_source == "heuristic":
        return "Análisis estimado con heurística de audio"
    if model_source == "ml_v3":
        return "Análisis con modelo v3 (audio + SpO2)"
    return f"Análisis con {model_source}"


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
        model_source=session.model_source,
        model_version=session.model_version,
        analysis_label=_analysis_label(session.model_source, session.model_version),
        continuidad=timeline,
        created_at=session.created_at,
    )


def _to_feedback_record(feedback: UserFeedback) -> SleepFeedbackRecord:
    return SleepFeedbackRecord(
        feedback_id=feedback.id,
        session_id=feedback.session_id,
        user_id=feedback.user_id,
        calificacion_descanso=feedback.sleep_rating,
        desperto_cansado=feedback.woke_tired,
        comentario=feedback.comment,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
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
) -> int:
    duration_hours = max((end_time - start_time).total_seconds() / 3600, 0)
    if duration_hours <= 0:
        return 0

    snore_frequency_per_hour = snore_count / max(duration_hours, 1 / 6)
    apnea_penalty = apnea_events * _APNEA_PENALTY_PER_EVENT
    snore_penalty = snore_frequency_per_hour * _SNORE_PENALTY_PER_HOUR

    score = (duration_hours * _SCORE_PER_HOUR) - apnea_penalty - snore_penalty

    return int(max(0, min(100, round(score))))


def _build_continuity_timeline_from_detections(
    detections: list[WindowDetection],
    duration_seconds: float,
) -> list[dict]:
    if duration_seconds <= 0:
        duration_seconds = max((detection.end_second for detection in detections), default=60.0)

    total_minutes = max(1, int(math.ceil(duration_seconds / 60)))
    minute_state = ["deep_sleep"] * total_minutes

    for detection in detections:
        if detection.label not in {LABEL_SNORE, LABEL_APNEA}:
            continue

        start_minute = max(0, int(detection.start_second // 60))
        end_minute = min(
            total_minutes - 1,
            int(max(detection.end_second - 1e-6, detection.start_second) // 60),
        )

        for minute in range(start_minute, end_minute + 1):
            minute_state[minute] = "interrupcion"

    step = 1 if total_minutes <= 180 else int(math.ceil(total_minutes / 180))
    timeline: list[dict] = []

    for minute in range(0, total_minutes, step):
        states = minute_state[minute : minute + step]
        state = "interrupcion" if "interrupcion" in states else "deep_sleep"
        timeline.append({"minuto": minute, "estado": state})

    return timeline


def _count_clustered_events(detections: list[WindowDetection], label: str) -> int:
    count = 0
    previous_match = False

    for detection in detections:
        current_match = detection.label == label
        if current_match and not previous_match:
            count += 1
        previous_match = current_match

    return count


def _estimate_ambient_noise(mean_rms_db: float | None) -> float | None:
    if mean_rms_db is None:
        return None

    normalized_db = max(0.0, min(120.0, mean_rms_db + 80.0))
    return round(normalized_db, 1)


def _analyze_session_fragments(session_id: str, total_duration_seconds: float) -> SessionAnalysisSummary | None:
    batch = build_session_audio_batch(
        session_id=session_id,
        fragment_root=_FRAGMENT_ROOT,
        sample_rate=16000,
        mfcc_coefficients=20,
    )

    if not batch.windows:
        return None

    inference = _sleep_model.classify_batch(batch)
    if not inference.detections:
        return None

    snore_count = _count_clustered_events(inference.detections, LABEL_SNORE)
    apnea_events = _count_clustered_events(inference.detections, LABEL_APNEA)

    effective_duration = batch.duration_seconds if batch.duration_seconds > 0 else total_duration_seconds
    continuity_timeline = _build_continuity_timeline_from_detections(
        detections=inference.detections,
        duration_seconds=effective_duration,
    )

    return SessionAnalysisSummary(
        snore_count=snore_count,
        apnea_events=apnea_events,
        continuity_timeline=continuity_timeline,
        ambient_noise_level=_estimate_ambient_noise(batch.mean_rms_db),
        detections=inference.detections,
        model_source=inference.source,
        model_version=inference.model_version,
    )


def _build_live_prediction_summary(predicciones: list[LivePrediction], snore_count: int, total_duration_seconds: float) -> SessionAnalysisSummary:
    apnea_events = sum(1 for pred in predicciones if pred.nivel in {"ALERTA", "CRITICO"})
    detections = [
        WindowDetection(
            window_index=pred.window_index,
            start_second=pred.start_second,
            end_second=pred.end_second,
            label=LABEL_APNEA if pred.nivel in {"ALERTA", "CRITICO"} else LABEL_NORMAL,
            confidence=float(max(0.05, min(0.99, pred.probabilidad))),
        )
        for pred in predicciones
    ]
    return SessionAnalysisSummary(
        snore_count=snore_count,
        apnea_events=apnea_events,
        continuity_timeline=_build_continuity_timeline_from_detections(
            detections=detections,
            duration_seconds=total_duration_seconds,
        ),
        ambient_noise_level=None,
        detections=detections,
        model_source="ml_v3",
        model_version="v3",
    )


def _persist_detection_logs(db: Session, session_id: str, analysis: SessionAnalysisSummary) -> None:
    if not analysis.detections:
        return

    records = [
        SleepDetectionLog(
            session_id=session_id,
            window_index=detection.window_index,
            start_second=detection.start_second,
            end_second=detection.end_second,
            label=detection.label,
            confidence_score=round(detection.confidence, 4),
            model_source=analysis.model_source,
            model_version=analysis.model_version,
        )
        for detection in analysis.detections
    ]
    db.add_all(records)


def _count_session_fragments(session_id: str) -> int:
    session_dir = _FRAGMENT_ROOT / session_id
    if not session_dir.exists():
        return 0
    return sum(1 for f in session_dir.iterdir() if f.is_file() and f.suffix.lower() in _ALLOWED_AUDIO_EXTENSIONS)


def _clear_session_fragment_state(session_id: str) -> None:
    cleanup_session_fragments(session_id=session_id, fragment_root=_FRAGMENT_ROOT)


def start_sleep_session(db: Session, user: User, payload: SleepSessionStartRequest) -> SleepSessionRecord:
    start_time = payload.start_time or datetime.now(UTC)

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
    session = get_user_sleep_session(db, session_id, user)
    if not session:
        raise SessionNotFoundError()

    if session.end_time is not None:
        raise SessionAlreadyFinishedError()

    end_time = payload.end_time or datetime.now(UTC)
    start_time = session.start_time

    # SQLite suele devolver datetime naive; normalizamos para comparar sin errores.
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=UTC)

    if end_time <= start_time:
        raise InvalidSessionTimeError()

    total_duration_seconds = max((end_time - start_time).total_seconds(), 0)
    analysis = _analyze_session_fragments(
        session_id=session_id,
        total_duration_seconds=total_duration_seconds,
    )

    session.end_time = end_time

    if analysis is not None:
        session.snore_count = analysis.snore_count
        session.apnea_events = analysis.apnea_events
        session.continuity_timeline = analysis.continuity_timeline
        session.model_source = analysis.model_source
        session.model_version = analysis.model_version
        if payload.ambient_noise_level is not None:
            session.ambient_noise_level = payload.ambient_noise_level
        elif analysis.ambient_noise_level is not None:
            session.ambient_noise_level = analysis.ambient_noise_level
        _persist_detection_logs(db=db, session_id=session_id, analysis=analysis)
    else:
        # Sin análisis de audio del servidor, usamos las predicciones v3 que el
        # teléfono calculó en vivo. Si tampoco hay, caemos a los contadores
        # reportados por el teléfono (heurísticos) marcándolos como estimación.
        if payload.predicciones:
            live_analysis = _build_live_prediction_summary(
                predicciones=payload.predicciones,
                snore_count=payload.snore_count,
                total_duration_seconds=total_duration_seconds,
            )
            session.snore_count = live_analysis.snore_count
            session.apnea_events = live_analysis.apnea_events
            session.continuity_timeline = live_analysis.continuity_timeline
            session.model_source = live_analysis.model_source
            session.model_version = live_analysis.model_version
            _persist_detection_logs(db=db, session_id=session_id, analysis=live_analysis)
        else:
            session.snore_count = payload.snore_count
            session.apnea_events = payload.apnea_events
            session.model_source = None
            session.model_version = None
            session.continuity_timeline = []
        if payload.ambient_noise_level is not None:
            session.ambient_noise_level = payload.ambient_noise_level

    session.avg_oxygen = payload.avg_oxygen

    session.sleep_score = _compute_sleep_score(
        start_time=start_time,
        end_time=end_time,
        snore_count=session.snore_count,
        apnea_events=session.apnea_events,
    )

    db.commit()
    db.refresh(session)
    _clear_session_fragment_state(session_id=session_id)

    return _to_record(session)


def list_sleep_sessions(
    db: Session,
    user: User,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[SleepSessionRecord], str | None]:
    query = select(SleepSession).where(SleepSession.user_id == user.id)

    if cursor:
        from app.models.pagination import decode_cursor
        cursor_dt = datetime.fromisoformat(decode_cursor(cursor))
        query = query.where(SleepSession.start_time < cursor_dt)

    query = query.order_by(SleepSession.start_time.desc()).limit(limit + 1)
    rows = db.scalars(query).all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        from app.models.pagination import encode_cursor
        next_cursor = encode_cursor(items[-1].start_time.isoformat())

    return [_to_record(item) for item in items], next_cursor


def list_sleep_detection_logs(
    db: Session,
    user: User,
    session_id: str,
    limit: int = 720,
) -> list[SleepDetectionLogRecord]:
    session = get_user_sleep_session(db, session_id, user)
    if not session:
        raise SessionNotFoundError()

    rows = db.scalars(
        select(SleepDetectionLog)
        .where(SleepDetectionLog.session_id == session_id)
        .order_by(SleepDetectionLog.window_index.asc(), SleepDetectionLog.id.asc())
        .limit(limit)
    ).all()

    return [
        SleepDetectionLogRecord(
            log_id=row.id,
            session_id=row.session_id,
            window_index=row.window_index,
            start_second=row.start_second,
            end_second=row.end_second,
            label=row.label,
            confidence_score=row.confidence_score,
            model_source=row.model_source,
            model_version=row.model_version,
            created_at=row.created_at,
        )
        for row in rows
    ]


def upsert_sleep_feedback(
    db: Session,
    user: User,
    session_id: str,
    payload: SleepFeedbackRequest,
) -> SleepFeedbackRecord:
    session = get_user_sleep_session(db, session_id, user)
    if not session:
        raise SessionNotFoundError()

    if session.end_time is None:
        raise ValueError("Solo puedes calificar sesiones finalizadas.")

    feedback = db.scalar(
        select(UserFeedback).where(UserFeedback.session_id == session_id, UserFeedback.user_id == user.id)
    )

    if feedback is None:
        feedback = UserFeedback(
            session_id=session_id,
            user_id=user.id,
            sleep_rating=payload.calificacion_descanso,
            woke_tired=payload.desperto_cansado,
            comment=payload.comentario,
        )
        db.add(feedback)
    else:
        feedback.sleep_rating = payload.calificacion_descanso
        feedback.woke_tired = payload.desperto_cansado
        feedback.comment = payload.comentario

    db.commit()
    db.refresh(feedback)

    return _to_feedback_record(feedback)


def _build_fragment_filename(fragment_index: int, source_name: str | None) -> str:
    source_suffix = Path(source_name or "").suffix.lower()
    suffix = source_suffix if source_suffix in _ALLOWED_AUDIO_EXTENSIONS else ".m4a"
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return f"fragment_{fragment_index:05d}_{timestamp}{suffix}"


async def ingest_sleep_fragment(
    db: Session,
    user: User,
    session_id: str,
    fragmento: UploadFile,
    fragment_index: int,
    duration_seconds: float | None,
) -> SleepFragmentUploadResponse:
    session = get_user_sleep_session(db, session_id, user)
    if not session:
        raise SessionNotFoundError()

    if session.end_time is not None:
        raise SessionAlreadyFinishedError()

    if fragmento.content_type and fragmento.content_type not in _ALLOWED_AUDIO_MIME_TYPES:
        raise ValueError(f"Tipo de archivo no soportado: {fragmento.content_type}")

    payload = await fragmento.read()
    if not payload:
        raise ValueError("Fragmento de audio vacío.")
    if len(payload) > settings.max_sleep_fragment_size_bytes:
        raise ValueError("Fragmento demasiado grande para procesamiento.")

    _FRAGMENT_ROOT.mkdir(parents=True, exist_ok=True)
    session_dir = _FRAGMENT_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    filename = _build_fragment_filename(fragment_index=fragment_index, source_name=fragmento.filename)
    stored_path = session_dir / filename
    stored_path.write_bytes(payload)

    created_at = datetime.now(UTC)
    queued_fragments = _count_session_fragments(session_id)

    return SleepFragmentUploadResponse(
        mensaje="Fragmento recibido para procesamiento temporal.",
        fragmento=SleepFragmentRecord(
            session_id=session_id,
            fragment_index=fragment_index,
            filename=filename,
            bytes_size=len(payload),
            duration_seconds=duration_seconds,
            queued_fragments=queued_fragments,
            created_at=created_at,
        ),
    )
