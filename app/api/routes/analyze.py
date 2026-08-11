from fastapi import APIRouter

from app.models.audio import AnalyzeResponse, AudioMetadata
from app.services.analyzer import analyze_audio_metadata

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(metadata: AudioMetadata) -> AnalyzeResponse:
    return analyze_audio_metadata(metadata)
