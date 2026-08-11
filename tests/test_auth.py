from fastapi.testclient import TestClient


def test_registro_exitoso(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Alejandro Usuario",
            "email": "alejandro.auth@example.com",
            "password": "ClaveSegura123",
            "ronca_habitualmente": True,
            "cansancio_diurno": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["access_token"]
    assert body["usuario"]["email"] == "alejandro.auth@example.com"
    assert body["usuario"]["ronca_habitualmente"] is True


def test_registro_duplicado(client: TestClient) -> None:
    payload = {
        "nombre_completo": "Cuenta Duplicada",
        "email": "duplicado@example.com",
        "password": "ClaveSegura123",
        "ronca_habitualmente": False,
        "cansancio_diurno": False,
        "acepta_consentimiento_datos": True,
        "acepta_disclaimer_medico": True,
    }

    first = client.post("/api/v1/auth/registro", json=payload)
    second = client.post("/api/v1/auth/registro", json=payload)

    assert first.status_code == 201
    assert second.status_code == 400


def test_login_y_perfil(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Perfil Usuario",
            "email": "perfil@example.com",
            "password": "ClaveSegura123",
            "ronca_habitualmente": False,
            "cansancio_diurno": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "perfil@example.com",
            "password": "ClaveSegura123",
        },
    )

    assert login.status_code == 200
    token = login.json()["access_token"]

    perfil = client.get(
        "/api/v1/auth/perfil",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert perfil.status_code == 200
    assert perfil.json()["email"] == "perfil@example.com"


def test_login_invalido(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "noexiste@example.com",
            "password": "ClaveSegura123",
        },
    )

    assert response.status_code == 401


def test_registro_rechazado_sin_consentimiento(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Sin Consentimiento",
            "email": "sin.consentimiento@example.com",
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": False,
            "acepta_disclaimer_medico": True,
        },
    )

    assert response.status_code == 400
