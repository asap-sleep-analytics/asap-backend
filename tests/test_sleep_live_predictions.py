from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Usuario Predicciones",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_finalizar_con_predicciones_v3_sin_audio(client: TestClient) -> None:
    token = _register(client, "live.v3@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "snore_count": 4,
            "apnea_events": 0,
            "avg_oxygen": 94.2,
            "predicciones": [
                {"window_index": 0, "start_second": 0, "end_second": 30, "nivel": "NORMAL", "probabilidad": 0.12},
                {"window_index": 1, "start_second": 30, "end_second": 60, "nivel": "ALERTA", "probabilidad": 0.61},
                {"window_index": 2, "start_second": 60, "end_second": 90, "nivel": "CRITICO", "probabilidad": 0.82},
            ],
        },
    )
    assert finish.status_code == 200

    body = finish.json()["sesion"]
    assert body["model_source"] == "ml_v3"
    assert body["model_version"] == "v3"
    assert body["apnea_events"] == 2
    assert body["snore_count"] == 4
    assert body["avg_oxygen"] == 94.2
    assert body["analysis_label"] == "Análisis con modelo v3 (audio + SpO2)"
    assert body["continuidad"]


def test_finalizar_sin_audio_ni_predicciones_cae_a_heuristica(client: TestClient) -> None:
    token = _register(client, "sin.predicciones@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 2, "apnea_events": 1},
    )
    assert finish.status_code == 200

    body = finish.json()["sesion"]
    assert body["model_source"] is None
    assert body["apnea_events"] == 1
