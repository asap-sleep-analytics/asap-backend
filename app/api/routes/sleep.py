from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.models.sleep import (
    SleepCalibrationRequest,
    SleepCalibrationResponse,
    SleepSessionFinishRequest,
    SleepSessionRecord,
    SleepSessionResponse,
    SleepSessionStartRequest,
)
from app.services.sleep import evaluate_noise_level, finish_sleep_session, list_sleep_sessions, start_sleep_session

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
