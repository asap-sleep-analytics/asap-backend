from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Health Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
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
    assert body["refresh_token"]

    new_profile = client.get(
        "/api/v1/auth/perfil",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert new_profile.status_code == 200


def test_refresh_con_refresh_token_sin_access_vigente(client: TestClient) -> None:
    registro = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Persistent Tester",
            "email": "refresh.persistent@example.com",
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert registro.status_code == 201
    refresh_token = registro.json()["refresh_token"]
    assert refresh_token

    # Sin Authorization header: solo el refresh token en el body.
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["usuario"]["email"] == "refresh.persistent@example.com"

    profile = client.get(
        "/api/v1/auth/perfil",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert profile.status_code == 200


def test_refresh_token_rotado_es_de_otro_tipo(client: TestClient) -> None:
    token = _register(client, "refresh.typ@example.com")

    # Un access token no sirve como refresh token (typ != refresh).
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )
    assert response.status_code == 401


def test_refresh_token_invalido_rechazado(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "token-falso-que-no-es-jwt"},
    )
    assert response.status_code == 401


def test_logout_revoca_tambien_el_refresh_token(client: TestClient) -> None:
    registro = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Revoke Tester",
            "email": "refresh.revoke@example.com",
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert registro.status_code == 201
    access = registro.json()["access_token"]
    refresh_token = registro.json()["refresh_token"]

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert logout.status_code == 204

    # El refresh token queda revocado por token_version.
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 401
