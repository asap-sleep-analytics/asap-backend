from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Health Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "database" in body
    assert "ml_model" in body


def test_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "asap_http_request_duration_seconds" in response.text


def test_logout_revokes_token(client: TestClient) -> None:
    token = _register(client, "logout@example.com")

    profile = client.get(
        "/api/v1/auth/perfil",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile.status_code == 200

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 204

    after_logout = client.get(
        "/api/v1/auth/perfil",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_logout.status_code == 401


def test_refresh_returns_new_token(client: TestClient) -> None:
    token = _register(client, "refresh@example.com")

    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["expires_in"] > 0

    new_profile = client.get(
        "/api/v1/auth/perfil",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert new_profile.status_code == 200
