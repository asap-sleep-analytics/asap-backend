from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "V3 Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_v3_predict_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sleep/v3/predict",
        files={"audio": ("a.wav", b"data", "audio/wav")},
        params={"spo2": "95,94,93"},
    )
    assert response.status_code == 401


def test_v3_predict_rejects_oversized_audio(client: TestClient) -> None:
    token = _register(client, "v3.big@example.com")
    response = client.post(
        "/api/v1/sleep/v3/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": ("a.wav", b"x" * (16 * 1024 * 1024), "audio/wav")},
        params={"spo2": "95,94,93"},
    )
    assert response.status_code == 400
    assert "demasiado grande" in response.json()["detail"].lower()


def test_v3_predict_rejects_invalid_modo(client: TestClient) -> None:
    token = _register(client, "v3.modo@example.com")
    response = client.post(
        "/api/v1/sleep/v3/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": ("a.wav", b"data", "audio/wav")},
        params={"spo2": "95,94,93", "modo": "inexistente"},
    )
    assert response.status_code == 400


def test_v3_health_reports_model_missing(client: TestClient) -> None:
    response = client.get("/api/v1/sleep/v3/health")
    assert response.status_code == 200
    assert response.json()["status"] == "model_missing"


def test_v3_predict_returns_503_without_models(client: TestClient) -> None:
    token = _register(client, "v3.noModel@example.com")
    response = client.post(
        "/api/v1/sleep/v3/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": ("a.wav", b"data", "audio/wav")},
        params={"spo2": "95,94,93", "modo": "screening"},
    )
    assert response.status_code == 503
