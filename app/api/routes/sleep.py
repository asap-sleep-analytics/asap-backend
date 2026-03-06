from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.models.sleep import (
    SleepCalibrationRequest,
    SleepCalibrationResponse,
    SleepDetectionLogRecord,
    SleepFeedbackRequest,
    SleepFeedbackResponse,
    SleepFragmentUploadResponse,
    SleepSessionFinishRequest,
    SleepSessionRecord,
    SleepSessionResponse,
    SleepSessionStartRequest,
)
from app.services.sleep import (
    evaluate_noise_level,
    finish_sleep_session,
    ingest_sleep_fragment,
    list_sleep_detection_logs,
    list_sleep_sessions,
    start_sleep_session,
    upsert_sleep_feedback,
)

router = APIRouter(prefix="/api/sleep", tags=["sleep"])


@router.post("/calibracion", response_model=SleepCalibrationResponse)
def calibration_endpoint(payload: SleepCalibrationRequest) -> SleepCalibrationResponse:
    return evaluate_noise_level(payload.ambient_noise_level)


@router.post("/sesiones/iniciar", response_model=SleepSessionResponse, status_code=status.HTTP_201_CREATED)
def start_session_endpoint(
    payload: SleepSessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionResponse:
    session = start_sleep_session(db=db, user=current_user, payload=payload)
    return SleepSessionResponse(mensaje="Monitoreo iniciado correctamente.", sesion=session)


@router.post("/sesiones/{session_id}/finalizar", response_model=SleepSessionResponse)
def finish_session_endpoint(
    session_id: str,
    payload: SleepSessionFinishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepSessionResponse:
    try:
        session = finish_sleep_session(db=db, user=current_user, session_id=session_id, payload=payload)
    except ValueError as exc:
        message = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "no encontrada" in message.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message) from exc

    return SleepSessionResponse(mensaje="Monitoreo finalizado. Reporte listo.", sesion=session)


@router.get("/sesiones", response_model=list[SleepSessionRecord])
def list_sessions_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SleepSessionRecord]:
    return list_sleep_sessions(db=db, user=current_user, limit=limit)


@router.post("/sesiones/{session_id}/feedback", response_model=SleepFeedbackResponse)
def upsert_session_feedback_endpoint(
    session_id: str,
    payload: SleepFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepFeedbackResponse:
    try:
        feedback = upsert_sleep_feedback(db=db, user=current_user, session_id=session_id, payload=payload)
    except ValueError as exc:
        message = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "no encontrada" in message.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message) from exc

    return SleepFeedbackResponse(mensaje="Feedback guardado correctamente.", feedback=feedback)


@router.get("/sesiones/{session_id}/detecciones", response_model=list[SleepDetectionLogRecord])
def list_session_detections_endpoint(
    session_id: str,
    limit: int = Query(default=720, ge=1, le=3000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SleepDetectionLogRecord]:
    try:
        return list_sleep_detection_logs(db=db, user=current_user, session_id=session_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/sesiones/{session_id}/fragmento",
    response_model=SleepFragmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fragment_endpoint(
    session_id: str,
    fragmento: UploadFile = File(...),
    fragment_index: int = Form(default=0, ge=0),
    duration_seconds: float | None = Form(default=None, ge=0),
    started_at: datetime | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SleepFragmentUploadResponse:
    _ = started_at  # Campo reservado para correlación de timestamps en futuras etapas de DSP.

    try:
        return await ingest_sleep_fragment(
            db=db,
            user=current_user,
            session_id=session_id,
            fragmento=fragmento,
            fragment_index=fragment_index,
            duration_seconds=duration_seconds,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "no encontrada" in message.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message) from exc
    finally:
        await fragmento.close()
