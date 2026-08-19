"""Verificación de ID tokens de proveedores OAuth (Google y Apple) vía JWKS.

El cliente (app móvil o web) obtiene el identity token del SDK del proveedor
y lo envía al backend. Este módulo valida firma, emisor, audiencia y caducidad
usando la clave pública descargada del JWKS del proveedor.
"""

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt

from app.core.config import settings

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_CACHE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class SocialIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    full_name: str | None


class SocialAuthError(ValueError):
    """Error de autenticación con proveedor externo con mensaje para el cliente."""


def _fetch_jwks(jwks_url: str) -> dict[str, Any]:
    cached_at, cached = _JWKS_CACHE.get(jwks_url, (0.0, {}))
    if cached and (time.time() - cached_at) < _JWKS_CACHE_TTL_SECONDS:
        return cached

    try:
        with urllib.request.urlopen(jwks_url, timeout=10) as response:  # noqa: S310 (URL de proveedor fijo)
            jwks = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SocialAuthError("No se pudo validar la sesión del proveedor. Intenta de nuevo.") from exc

    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise SocialAuthError("Respuesta inválida del proveedor de autenticación.")

    _JWKS_CACHE[jwks_url] = (time.time(), jwks)
    return jwks


def _get_public_key(jwks: dict[str, Any], token_headers: dict[str, Any]) -> jwt.PyJWK:
    kid = token_headers.get("kid")
    for key in jwks.get("keys", []):
        if kid and key.get("kid") == kid:
            try:
                return jwt.PyJWK.from_dict(key)
            except Exception as exc:  # noqa: BLE001
                raise SocialAuthError("Clave pública inválida del proveedor.") from exc
    raise SocialAuthError("No se encontró la clave del proveedor para validar la sesión.")


def _decode_token(
    id_token: str,
    jwks_url: str,
    audience: str | list[str],
    issuer: str | set[str],
) -> dict[str, Any]:
    try:
        token_headers = jwt.get_unverified_header(id_token)
    except jwt.InvalidTokenError as exc:
        raise SocialAuthError("El token del proveedor no es válido.") from exc

    jwks = _fetch_jwks(jwks_url)
    public_key = _get_public_key(jwks, token_headers)

    try:
        return jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise SocialAuthError("La sesión del proveedor está vencida. Vuelve a iniciar sesión.") from exc
    except jwt.InvalidTokenError as exc:
        raise SocialAuthError("La sesión del proveedor no es válida.") from exc


def verify_id_token(provider: str, id_token: str) -> SocialIdentity:
    if provider == "google":
        client_ids = settings.google_client_ids
        if not client_ids:
            raise SocialAuthError("El inicio de sesión con Google no está habilitado todavía.")
        payload = _decode_token(id_token, GOOGLE_JWKS_URL, client_ids, GOOGLE_ISSUERS)
        email = payload.get("email")
        if not email:
            raise SocialAuthError("Google no proporcionó un correo para esta cuenta.")
        return SocialIdentity(
            provider="google",
            subject=str(payload["sub"]),
            email=email.strip().lower(),
            email_verified=bool(payload.get("email_verified", False)),
            full_name=(payload.get("name") or None),
        )

    if provider == "apple":
        client_id = settings.apple_client_id
        if not client_id:
            raise SocialAuthError("El inicio de sesión con Apple no está habilitado todavía.")
        payload = _decode_token(id_token, APPLE_JWKS_URL, client_id, APPLE_ISSUER)
        email = payload.get("email")
        subject = str(payload["sub"])
        return SocialIdentity(
            provider="apple",
            subject=subject,
            email=email.strip().lower() if email else None,
            email_verified=bool(payload.get("email_verified", False)),
            full_name=None,
        )

    raise SocialAuthError("Proveedor de inicio de sesión no soportado.")
