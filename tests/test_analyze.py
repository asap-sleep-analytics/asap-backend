from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_analyze_endpoint_returns_response_schema() -> None:
    payload = {
        "file_name": "subject_001.wav",
        "duration_seconds": 35.5,
        "sample_rate_hz": 22050,
        "channels": 1,
        "codec": "pcm_s16le",
        "patient_id": "PT-001",
        "extra": {"device": "wearable-v2"},
    }

    response = client.post("/analyze", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "quality_score" in body
    assert "insights" in body
