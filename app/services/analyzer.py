from app.models.audio import AnalyzeResponse, AudioMetadata


def analyze_audio_metadata(metadata: AudioMetadata) -> AnalyzeResponse:
    quality_score = 100.0
    insights: list[str] = []

    if metadata.sample_rate_hz < 16000:
        quality_score -= 25
        insights.append("Sample rate below 16 kHz may reduce respiratory event fidelity.")

    if metadata.duration_seconds < 10:
        quality_score -= 20
        insights.append("Audio duration is short for robust apnea screening.")

    if metadata.channels == 1:
        insights.append("Mono audio detected; accepted for baseline analysis.")

    if not metadata.codec:
        quality_score -= 5
        insights.append("Codec not provided; downstream DSP assumptions may be less reliable.")

    quality_score = max(0.0, round(quality_score, 2))
    status = "ready" if quality_score >= 70 else "review"

    if not insights:
        insights.append("Metadata quality is suitable for ML preprocessing.")

    return AnalyzeResponse(status=status, quality_score=quality_score, insights=insights)
