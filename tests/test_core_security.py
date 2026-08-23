import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from passlib import exc as passlib_exc

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    revoke_user_tokens,
    verify_password,
)


def test_hash_and_verify_password_roundtrip() -> None:
    hashed = hash_password("ClaveSegura123")
    assert hashed != "ClaveSegura123"
    assert hashed.startswith("$2")  # bcrypt
    assert verify_password("ClaveSegura123", hashed) is True
    assert verify_password("OtraClave", hashed) is False


def test_verify_password_rechaza_valores_invalidos() -> None:
    hashed = hash_password("ClaveSegura123")
    assert verify_password("", hashed) is False
    assert verify_password("ClaveSegura124", hashed) is False

    # Hash malformado: passlib no puede identificar el esquema y lanza error.
    with pytest.raises(passlib_exc.UnknownHashError):
        verify_password("x", "no-es-un-hash-bcrypt")


def test_create_access_token_payload_y_expiracion() -> None:
    token, expires_in = create_access_token("user-123", "ana@example.com", token_version=2)

    assert expires_in == settings.auth_access_token_expires_minutes * 60
    assert token

    payload = jwt.decode(
        token,
        settings.auth_secret_key,
        algorithms=[settings.auth_algorithm],
        options={"verify_signature": True},
    )
    assert payload["sub"] == "user-123"
    assert payload["email"] == "ana@example.com"
    assert payload["iss"] == settings.auth_issuer
    assert payload["ver"] == 2
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload


def test_decode_access_token_roundtrip() -> None:
    token, _ = create_access_token("user-456", "luis@example.com")
    payload = decode_access_token(token)

    assert payload["sub"] == "user-456"
    assert payload["email"] == "luis@example.com"
    assert payload["ver"] == 1


def test_decode_token_expirado_lanza_401() -> None:
    payload = {
        "sub": "user-999",
        "email": "old@example.com",
        "iss": settings.auth_issuer,
        "jti": "abc",
        "ver": 1,
        "iat": datetime.now(UTC) - timedelta(hours=1),
        "exp": datetime.now(UTC) - timedelta(minutes=5),
    }
    token = jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401
    assert "vencido" in exc_info.value.detail


def test_decode_token_manipulado_lanza_401() -> None:
    token, _ = create_access_token("user-789", "hacker@example.com")
    token_manipulado = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token_manipulado)
    assert exc_info.value.status_code == 401


def test_decode_token_con_issuer_incorrecto_lanza_401() -> None:
    payload = {
        "sub": "user-1",
        "email": "x@example.com",
        "iss": "otro-emisor",
        "jti": "abc",
        "ver": 1,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=15),
    }
    token = jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_decode_token_con_firma_de_otra_clave_lanza_401() -> None:
    payload = {
        "sub": "user-1",
        "email": "x@example.com",
        "iss": settings.auth_issuer,
        "jti": "abc",
        "ver": 1,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=15),
    }
    token = jwt.encode(payload, "clave-distinta-para-el-test", algorithm=settings.auth_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_revoke_user_tokens_incrementa_version(db_session) -> None:
    from app.db.models import User

    user = User(
        full_name="Revoca Test",
        email=f"revoca-{uuid.uuid4().hex}@example.com",
        password_hash="hasheado",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    version_inicial = user.token_version

    revoke_user_tokens(db_session, user)
    db_session.refresh(user)
    assert user.token_version == version_inicial + 1


def test_token_expira_realmente_con_el_tiempo(client) -> None:
    token, _ = create_access_token("user-time", "time@example.com")
    payload = decode_access_token(token)
    assert payload["exp"] > int(time.time())
