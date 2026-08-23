from fastapi.testclient import TestClient

REGISTER_PAYLOAD = {
    "nombre_completo": "Usuario Borrado",
    "email": "borrado@example.com",
    "password": "ClaveSegura123",
    "ronca_habitualmente": False,
    "cansancio_diurno": False,
    "acepta_terminos_condiciones": True,
    "acepta_consentimiento_datos": True,
    "acepta_disclaimer_medico": True,
}


def _register_and_start_session(client: TestClient) -> tuple[str, str]:
    created = client.post("/api/v1/auth/registro", json=REGISTER_PAYLOAD)
    assert created.status_code == 201
    token = created.json()["access_token"]

    session = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert session.status_code == 201
    return token, session.json()["sesion"]["session_id"]


def test_borrado_cuenta_elimina_datos_y_sesion(client: TestClient) -> None:
    token, session_id = _register_and_start_session(client)
    auth_headers = {"Authorization": f"Bearer {token}"}

    perfil_antes = client.get("/api/v1/auth/perfil", headers=auth_headers)
    assert perfil_antes.status_code == 200

    borrado = client.delete("/api/v1/auth/cuenta", headers=auth_headers)
    assert borrado.status_code == 204

    perfil_despues = client.get("/api/v1/auth/perfil", headers=auth_headers)
    assert perfil_despues.status_code == 401


def test_borrado_cuenta_permite_volver_a_registrarse(client: TestClient) -> None:
    token, _ = _register_and_start_session(client)

    borrado = client.delete(
        "/api/v1/auth/cuenta",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert borrado.status_code == 204

    re_registro = client.post("/api/v1/auth/registro", json=REGISTER_PAYLOAD)
    assert re_registro.status_code == 201


def test_borrado_cuenta_sin_token(client: TestClient) -> None:
    response = client.delete("/api/v1/auth/cuenta")
    assert response.status_code == 401
