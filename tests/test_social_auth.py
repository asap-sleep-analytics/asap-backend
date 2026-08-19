import pytest
from fastapi.testclient import TestClient

from app.services.social_auth import SocialAuthError, SocialIdentity, verify_id_token


def _social_payload(provider: str = "google", **overrides) -> dict:
    payload = {
        "provider": provider,
        "id_token": "fake-id-token",
        "acepta_terminos_condiciones": True,
        "acepta_consentimiento_datos": True,
        "acepta_disclaimer_medico": True,
    }
    payload.update(overrides)
    return payload


def test_social_login_google_crea_cuenta(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(provider: str, id_token: str) -> SocialIdentity:
        return SocialIdentity(
            provider="google",
            subject="sub-google-1",
            email="nuevo.social@example.com",
            email_verified=True,
            full_name="Nuevo Social",
        )

    monkeypatch.setattr("app.services.auth.verify_id_token", fake_verify)

    response = client.post("/api/v1/auth/social/login", json=_social_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["access_token"]
    assert body["usuario"]["email"] == "nuevo.social@example.com"
    assert body["usuario"]["nombre_completo"] == "Nuevo Social"
    assert body["usuario"]["metodo_ingreso"] == "google"


def test_social_login_reusa_cuenta_existente(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = SocialIdentity(
        provider="google",
        subject="sub-google-2",
        email="reuso.social@example.com",
        email_verified=True,
        full_name="Reuso Social",
    )

    def fake_verify(provider: str, id_token: str) -> SocialIdentity:
        return identity

    monkeypatch.setattr("app.services.auth.verify_id_token", fake_verify)

    first = client.post("/api/v1/auth/social/login", json=_social_payload())
    second = client.post("/api/v1/auth/social/login", json=_social_payload())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["usuario"]["user_id"] == second.json()["usuario"]["user_id"]


def test_social_login_apple_sin_email_por_subject(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = SocialIdentity(
        provider="apple",
        subject="sub-apple-1",
        email="apple.user@example.com",
        email_verified=True,
        full_name="Apple User",
    )

    def fake_verify(provider: str, id_token: str) -> SocialIdentity:
        return identity

    monkeypatch.setattr("app.services.auth.verify_id_token", fake_verify)

    first = client.post("/api/v1/auth/social/login", json=_social_payload(provider="apple"))
    assert first.status_code == 200

    sin_email = SocialIdentity(
        provider="apple",
        subject="sub-apple-1",
        email=None,
        email_verified=True,
        full_name=None,
    )
    monkeypatch.setattr("app.services.auth.verify_id_token", lambda provider, id_token: sin_email)

    second = client.post("/api/v1/auth/social/login", json=_social_payload(provider="apple"))
    assert second.status_code == 200
    assert second.json()["usuario"]["user_id"] == first.json()["usuario"]["user_id"]


def test_social_login_vincula_cuenta_local_por_email(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Local User",
            "email": "vinculo.social@example.com",
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )

    def fake_verify(provider: str, id_token: str) -> SocialIdentity:
        return SocialIdentity(
            provider="google",
            subject="sub-google-3",
            email="vinculo.social@example.com",
            email_verified=True,
            full_name=None,
        )

    monkeypatch.setattr("app.services.auth.verify_id_token", fake_verify)

    response = client.post("/api/v1/auth/social/login", json=_social_payload())
    assert response.status_code == 200
    assert response.json()["usuario"]["email"] == "vinculo.social@example.com"
    assert response.json()["usuario"]["metodo_ingreso"] == "google"


def test_social_login_requiere_terminos_para_cuenta_nueva(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(provider: str, id_token: str) -> SocialIdentity:
        return SocialIdentity(
            provider="google",
            subject="sub-google-4",
            email="sin.terminos.social@example.com",
            email_verified=True,
            full_name=None,
        )

    monkeypatch.setattr("app.services.auth.verify_id_token", fake_verify)

    response = client.post(
        "/api/v1/auth/social/login",
        json=_social_payload(acepta_terminos_condiciones=False),
    )
    assert response.status_code == 400


def test_social_login_token_invalido(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.social_auth import SocialAuthError

    def fake_verify(provider: str, id_token: str) -> SocialIdentity:
        raise SocialAuthError("La sesión del proveedor no es válida.")

    monkeypatch.setattr("app.services.auth.verify_id_token", fake_verify)

    response = client.post("/api/v1/auth/social/login", json=_social_payload())
    assert response.status_code == 401


def test_provider_sin_configurar_no_hace_red(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "google_client_ids", [])

    with pytest.raises(SocialAuthError, match="no está habilitado"):
        verify_id_token("google", "fake-token")


def test_provider_no_soportado() -> None:
    with pytest.raises(SocialAuthError, match="no soportado"):
        verify_id_token("facebook", "fake-token")
