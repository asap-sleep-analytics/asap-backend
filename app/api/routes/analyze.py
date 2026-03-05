from fastapi import APIRouter

from app.models.audio import AnalyzeResponse, AudioMetadata
from app.services.analyzer import analyze_audio_metadata

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse, tags=["analysis"])
def analyze(metadata: AudioMetadata) -> AnalyzeResponse:
    return analyze_audio_metadata(metadata)
