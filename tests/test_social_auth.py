"""Pruebas unitarias de verificación de ID tokens OAuth.

Se generan claves criptográficas reales (RSA y EC P-256), se construye un JWKS
falso y se firma un token con la clave privada, de forma que la validación
completa (firma, emisor, audiencia, caducidad) se ejercita de verdad sin red.
"""

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.core.config import settings
from app.services import social_auth
from app.services.social_auth import SocialAuthError, SocialIdentity, verify_id_token

GOOGLE_KID = "test-google-kid"
APPLE_KID = "test-apple-kid"
FAKE_AUDIENCE = "fake-client-id.apps.googleusercontent.com"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _rsa_n_e(public_key: rsa.RSAPublicKey) -> tuple[str, str]:
    numbers = public_key.public_numbers()
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return _b64url(n_bytes), _b64url(e_bytes)


def _ec_x_y(public_key: ec.EllipticCurvePublicKey) -> tuple[str, str]:
    numbers = public_key.public_numbers()
    curve_size = (numbers.curve.key_size + 7) // 8
    return _b64url(numbers.x.to_bytes(curve_size, "big")), _b64url(
        numbers.y.to_bytes(curve_size, "big")
    )


def _token(private_key, alg: str, kid: str, payload: dict) -> str:
    return social_auth.jwt.encode(
        payload,
        private_key,
        algorithm=alg,
        headers={"kid": kid},
    )


@pytest.fixture(scope="module")
def google_jwks() -> dict:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n, e = _rsa_n_e(private_key.public_key())
    social_auth._RSA_TEST_KEY = private_key  # type: ignore[attr-defined]
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": GOOGLE_KID,
                "n": n,
                "e": e,
            }
        ]
    }


@pytest.fixture(scope="module")
def apple_jwks() -> dict:
    private_key = ec.generate_private_key(curve=ec.SECP256R1())
    x, y = _ec_x_y(private_key.public_key())
    social_auth._APPLE_TEST_KEY = private_key  # type: ignore[attr-defined]
    return {
        "keys": [
            {
                "kty": "EC",
                "use": "sig",
                "alg": "ES256",
                "crv": "P-256",
                "kid": APPLE_KID,
                "x": x,
                "y": y,
                "n": "",
                "e": "",
            }
        ]
    }


def _google_token(
    *,
    kid: str = GOOGLE_KID,
    aud: str = FAKE_AUDIENCE,
    iss: str = "https://accounts.google.com",
    email: str = "Ana.Garcia@Example.com",
    email_verified: bool = True,
    exp_offset_minutes: int = 15,
    name: str | None = "Ana García",
) -> str:
    import time
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": "google-uid-12345",
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "iat": int(now.timestamp()) - 60,
        "exp": int((now + timedelta(minutes=exp_offset_minutes)).timestamp()),
        "nbf": int(time.time()) - 300,
    }
    private_key: rsa.RSAPrivateKey = social_auth._RSA_TEST_KEY  # type: ignore[attr-defined]
    return _token(private_key, "RS256", kid, payload)


def _apple_token(
    *,
    email: str | None = "luis@icloud.com",
    email_verified: bool = True,
    exp_offset_minutes: int = 15,
) -> str:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": "com.asap.bundle.id",
        "sub": "apple-uid-999",
        "email": email,
        "iat": int(now.timestamp()) - 60,
        "exp": int((now + timedelta(minutes=exp_offset_minutes)).timestamp()),
    }
    if email:
        payload["email_verified"] = email_verified
    private_key: ec.EllipticCurvePrivateKey = social_auth._APPLE_TEST_KEY  # type: ignore[attr-defined]
    return _token(private_key, "ES256", APPLE_KID, payload)


@pytest.fixture()
def mock_jwks(monkeypatch: pytest.MonkeyPatch, google_jwks: dict, apple_jwks: dict):
    def _fake_fetch(url: str) -> dict:
        if url == social_auth.GOOGLE_JWKS_URL:
            return google_jwks
        if url == social_auth.APPLE_JWKS_URL:
            return apple_jwks
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(social_auth, "_fetch_jwks", _fake_fetch)
    monkeypatch.setattr(settings, "google_client_ids", [FAKE_AUDIENCE])
    monkeypatch.setattr(settings, "apple_client_id", "com.asap.bundle.id")
    return monkeypatch


class TestGoogle:
    def test_token_valido_devuelve_identity_normalizada(
        self, mock_jwks: pytest.MonkeyPatch
    ) -> None:
        identity = verify_id_token("google", _google_token())

        assert isinstance(identity, SocialIdentity)
        assert identity.provider == "google"
        assert identity.subject == "google-uid-12345"
        assert identity.email == "ana.garcia@example.com"
        assert identity.email_verified is True
        assert identity.full_name == "Ana García"

    def test_token_email_no_verificado(self, mock_jwks: pytest.MonkeyPatch) -> None:
        identity = verify_id_token("google", _google_token(email_verified=False))
        assert identity.email_verified is False

    def test_token_sin_nombre(self, mock_jwks: pytest.MonkeyPatch) -> None:
        identity = verify_id_token("google", _google_token(name=None))
        assert identity.full_name is None

    def test_token_sin_email_rechazado(self, mock_jwks: pytest.MonkeyPatch) -> None:
        with pytest.raises(SocialAuthError, match="no proporcionó un correo"):
            verify_id_token("google", _google_token(email=None))

    def test_token_expirado_rechazado(self, mock_jwks: pytest.MonkeyPatch) -> None:
        with pytest.raises(SocialAuthError, match="está vencida"):
            verify_id_token("google", _google_token(exp_offset_minutes=-5))

    def test_token_audiencia_incorrecta_rechazado(
        self, mock_jwks: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(SocialAuthError, match="no es válida"):
            verify_id_token("google", _google_token(aud="otra-app-id"))

    def test_token_issuer_incorrecto_rechazado(
        self, mock_jwks: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(SocialAuthError, match="no es válida"):
            verify_id_token("google", _google_token(iss="https://evil.example.com"))

    def test_token_kid_desconocido_rechazado(self, mock_jwks: pytest.MonkeyPatch) -> None:
        with pytest.raises(SocialAuthError, match="No se encontró la clave"):
            verify_id_token("google", _google_token(kid="otro-kid"))

    def test_token_firmado_por_otra_clave_rechazado(
        self, mock_jwks: pytest.MonkeyPatch
    ) -> None:
        otro_par = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _google_token()
        partes = token.split(".")
        # Firmamos el mismo encabezado+payload con otra clave.
        payload_b64 = partes[1]
        header_b64 = partes[0]
        firma = social_auth.jwt.encode(
            {"_x": "x"},
            otro_par,
            algorithm="RS256",
            headers={"kid": GOOGLE_KID},
        ).split(".")[2]
        tampered = f"{header_b64}.{payload_b64}.{firma}"

        with pytest.raises(SocialAuthError, match="no es válida"):
            verify_id_token("google", tampered)

    def test_google_no_habilitado(self, mock_jwks: pytest.MonkeyPatch) -> None:
        mock_jwks.setattr(settings, "google_client_ids", [])
        with pytest.raises(SocialAuthError, match="no está habilitado"):
            verify_id_token("google", _google_token())


class TestApple:
    def test_token_valido_con_email(self, mock_jwks: pytest.MonkeyPatch) -> None:
        identity = verify_id_token("apple", _apple_token())

        assert identity.provider == "apple"
        assert identity.subject == "apple-uid-999"
        assert identity.email == "luis@icloud.com"
        assert identity.full_name is None

    def test_token_sin_email_devuelve_email_none(
        self, mock_jwks: pytest.MonkeyPatch
    ) -> None:
        identity = verify_id_token("apple", _apple_token(email=None))
        assert identity.email is None
        assert identity.email_verified is False

    def test_token_issuer_incorrecto_rechazado(
        self, mock_jwks: pytest.MonkeyPatch
    ) -> None:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        payload = {
            "iss": "https://evil.apple.example.com",
            "aud": "com.asap.bundle.id",
            "sub": "apple-uid",
            "email": "x@example.com",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
        }
        private_key: ec.EllipticCurvePrivateKey = social_auth._APPLE_TEST_KEY  # type: ignore[attr-defined]
        token = _token(private_key, "ES256", APPLE_KID, payload)

        with pytest.raises(SocialAuthError, match="no es válida"):
            verify_id_token("apple", token)

    def test_apple_no_habilitado(self, mock_jwks: pytest.MonkeyPatch) -> None:
        mock_jwks.setattr(settings, "apple_client_id", "")
        with pytest.raises(SocialAuthError, match="no está habilitado"):
            verify_id_token("apple", _apple_token())


def test_provider_no_soportado(mock_jwks: pytest.MonkeyPatch) -> None:
    with pytest.raises(SocialAuthError, match="no soportado"):
        verify_id_token("facebook", "token-fake")


def test_token_no_es_un_jwt_malformado(mock_jwks: pytest.MonkeyPatch) -> None:
    with pytest.raises(SocialAuthError, match="no es válido"):
        verify_id_token("google", "esto-no-es-un-jwt")
