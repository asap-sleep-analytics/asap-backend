from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Usuario Dashboard",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_dashboard_resumen_auth_required(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/resumen")
    assert response.status_code == 401


def test_dashboard_resumen_ok(client: TestClient) -> None:
    token = _register(client, "dashboard@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ambient_noise_level": 38,
        },
    )
    assert start.status_code == 201

    session_id = start.json()["sesion"]["session_id"]
    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "snore_count": 12,
            "apnea_events": 3,
            "avg_oxygen": 95,
            "ambient_noise_level": 42,
        },
    )
    assert finish.status_code == 200

    response = client.get(
        "/api/v1/dashboard/resumen",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["usuario"]["email"] == "dashboard@example.com"
    assert body["indicadores"]["sleep_score"] >= 0
    assert body["indicadores"]["eventos_apnea_ronquido"]["total"] == 15
    assert isinstance(body["indicadores"]["continuidad"], list)
    assert body["disclaimer_medico"]
    assert len(body["sugerencias"]) >= 1
