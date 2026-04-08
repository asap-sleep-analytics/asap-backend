from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.models.sleep_v3 import SleepV3HealthResponse, SleepV3ModosResponse, SleepV3PredictResponse
from app.services.ml_v3 import describe_modes, health_payload, predict_dual_mode

router = APIRouter(prefix="/api/sleep/v3", tags=["sleep-v3"])


@router.get("/health", response_model=SleepV3HealthResponse)
def sleep_v3_health() -> SleepV3HealthResponse:
    return SleepV3HealthResponse(**health_payload())


@router.get("/modos", response_model=SleepV3ModosResponse)
def sleep_v3_modes() -> SleepV3ModosResponse:
    return SleepV3ModosResponse(modos=describe_modes())


@router.post("/predict", response_model=SleepV3PredictResponse)
async def sleep_v3_predict(
    audio: UploadFile = File(..., description="Audio WAV de 30s grabado pasivamente"),
    spo2: str = Query(default="95,95,94,94,95", description="Valores SpO2 separados por coma"),
    modo: str = Query(default="screening", description="Modo clinico: screening o seguimiento"),
    perfil: str = Query(default="general", description="Perfil del paciente"),
) -> SleepV3PredictResponse:
    try:
        payload = await predict_dual_mode(audio=audio, spo2=spo2, modo=modo, perfil=perfil)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await audio.close()

    return SleepV3PredictResponse(**payload)
