from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app.services.auth as auth_service


def _register(
    client: TestClient,
    email: str,
    nombre: str = "Usuario Prueba",
    password: str = "ClaveSegura123",
) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": nombre,
            "email": email,
            "password": password,
            "ronca_habitualmente": False,
            "cansancio_diurno": False,
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _extract_token_from_url(url: str) -> str:
    token = parse_qs(urlparse(url).query).get("token", [""])[0]
    assert token, "URL no contiene un token"
    return token


def test_registro_exitoso(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Alejandro Usuario",
            "email": "alejandro.auth@example.com",
            "password": "ClaveSegura123",
            "ronca_habitualmente": True,
            "cansancio_diurno": True,
            "acepta_terminos_condiciones": True,
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
        "acepta_terminos_condiciones": True,
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
            "acepta_terminos_condiciones": True,
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


def test_registro_rechazado_sin_terminos(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Sin Terminos",
            "email": "sin.terminos@example.com",
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": False,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )

    assert response.status_code == 400


class TestVerificacionEmail:
    def test_registro_reporta_email_no_verificado(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/auth/registro",
            json={
                "nombre_completo": "Verificar Cuenta",
                "email": "verificar@example.com",
                "password": "ClaveSegura123",
                "ronca_habitualmente": False,
                "cansancio_diurno": False,
                "acepta_terminos_condiciones": True,
                "acepta_consentimiento_datos": True,
                "acepta_disclaimer_medico": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["usuario"]["email_verificado"] is False

    def test_envio_devuelve_url_preview_y_verifica(
        self, client: TestClient
    ) -> None:
        token = _register(client, "verifica.preview@example.com")
        envio = client.post(
            "/api/v1/auth/email/enviar-verificacion",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert envio.status_code == 200
        body = envio.json()
        assert body["verificacion_url_preview"], "SMTP no configurado debe devolver preview"

        url = body["verificacion_url_preview"]
        verify_token = _extract_token_from_url(url)

        verificacion = client.get(f"/api/v1/auth/email/verificar?token={verify_token}")
        assert verificacion.status_code == 200
        assert "verificado" in verificacion.json()["mensaje"].lower()

        perfil = client.get(
            "/api/v1/auth/perfil",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert perfil.json()["email_verificado"] is True

    def test_verificar_dos_veces_reporta_ya_verificado(
        self, client: TestClient
    ) -> None:
        token = _register(client, "verifica.repetido@example.com")
        envio = client.post(
            "/api/v1/auth/email/enviar-verificacion",
            headers={"Authorization": f"Bearer {token}"},
        )
        verify_token = _extract_token_from_url(envio.json()["verificacion_url_preview"])

        first = client.get(f"/api/v1/auth/email/verificar?token={verify_token}")
        second = client.get(f"/api/v1/auth/email/verificar?token={verify_token}")
        assert first.status_code == 200
        assert second.status_code == 200
        assert "ya" in second.json()["mensaje"].lower()

    def test_token_invalido_rechazado(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/email/verificar?token=token-invalido")
        assert response.status_code == 400

    def test_token_expirado_rechazado(
        self, client: TestClient, db_session
    ) -> None:
        token = _register(client, "verifica.expirado@example.com")
        envio = client.post(
            "/api/v1/auth/email/enviar-verificacion",
            headers={"Authorization": f"Bearer {token}"},
        )
        verify_token = _extract_token_from_url(envio.json()["verificacion_url_preview"])

        from app.db.models import User

        user = db_session.scalar(
            auth_service.select(User).where(User.email == "verifica.expirado@example.com")
        )
        assert user is not None
        user.email_verify_token_expires_at = datetime.now(UTC) - timedelta(minutes=5)
        db_session.commit()

        response = client.get(f"/api/v1/auth/email/verificar?token={verify_token}")
        assert response.status_code == 400
        assert "expir" in response.json()["detail"]

    def test_envio_requiere_autenticacion(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/email/enviar-verificacion")
        assert response.status_code == 401


class TestRecuperacionPassword:
    def test_olvidada_no_revela_si_el_correo_existe(self, client: TestClient) -> None:
        _register(client, "pwd.forgot@example.com")
        mensaje_con_registro = client.post(
            "/api/v1/auth/password/olvidada",
            json={"email": "pwd.forgot@example.com"},
        )
        mensaje_sin_registro = client.post(
            "/api/v1/auth/password/olvidada",
            json={"email": "nadie@example.com"},
        )
        assert mensaje_con_registro.status_code == 200
        assert mensaje_sin_registro.status_code == 200
        assert (
            mensaje_con_registro.json()["mensaje"]
            == mensaje_sin_registro.json()["mensaje"]
        )

    def test_restablecer_permite_entrar_con_la_nueva_clave(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _register(client, "pwd.reset@example.com", password="ClaveOriginal1")
        urls_enviadas: list[str] = []

        def _fake_send(name: str, email: str, reset_url: str) -> bool:
            urls_enviadas.append(reset_url)
            return True

        monkeypatch.setattr(auth_service, "send_password_reset_email", _fake_send)

        solicitud = client.post(
            "/api/v1/auth/password/olvidada",
            json={"email": "pwd.reset@example.com"},
        )
        assert solicitud.status_code == 200
        assert len(urls_enviadas) == 1

        reset_token = _extract_token_from_url(urls_enviadas[0])
        restablecer = client.post(
            "/api/v1/auth/password/restablecer",
            json={"token": reset_token, "nueva_password": "ClaveNueva456"},
        )
        assert restablecer.status_code == 200

        login_antigua = client.post(
            "/api/v1/auth/login",
            json={"email": "pwd.reset@example.com", "password": "ClaveOriginal1"},
        )
        assert login_antigua.status_code == 401

        login_nueva = client.post(
            "/api/v1/auth/login",
            json={"email": "pwd.reset@example.com", "password": "ClaveNueva456"},
        )
        assert login_nueva.status_code == 200

    def test_restablecer_invalida_tokens_anteriores(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token_viejo = _register(client, "pwd.revoke@example.com", password="ClaveOriginal1")
        urls_enviadas: list[str] = []

        def _fake_send(name: str, email: str, reset_url: str) -> bool:
            urls_enviadas.append(reset_url)
            return True

        monkeypatch.setattr(auth_service, "send_password_reset_email", _fake_send)
        client.post(
            "/api/v1/auth/password/olvidada",
            json={"email": "pwd.revoke@example.com"},
        )
        reset_token = _extract_token_from_url(urls_enviadas[0])
        client.post(
            "/api/v1/auth/password/restablecer",
            json={"token": reset_token, "nueva_password": "ClaveNueva456"},
        )

        antiguo_perfil = client.get(
            "/api/v1/auth/perfil",
            headers={"Authorization": f"Bearer {token_viejo}"},
        )
        assert antiguo_perfil.status_code == 401

    def test_token_invalido_rechazado(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/password/restablecer",
            json={"token": "token-invalido", "nueva_password": "ClaveNueva456"},
        )
        assert response.status_code == 400
