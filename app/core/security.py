import logging
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, email: str, token_version: int = 1) -> tuple[str, int]:
    expires_minutes = settings.auth_access_token_expires_minutes
    expires_delta = timedelta(minutes=expires_minutes)
    expire = datetime.now(UTC) + expires_delta

    payload = {
        "sub": user_id,
        "email": email,
        "iss": settings.auth_issuer,
        "jti": uuid.uuid4().hex,
        "ver": token_version,
        "iat": datetime.now(UTC),
        "exp": expire,
    }

    token = jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)
    return token, int(expires_delta.total_seconds())


def create_refresh_token(user_id: str, email: str, token_version: int = 1) -> tuple[str, int]:
    """Refresh token de larga duración para sesiones persistentes.

    Se valida firma, tipo y versión (revocación) pero NO expiración corta:
    vive `auth_refresh_token_expires_days` días y se rota en cada uso.
    """
    expires_days = max(settings.auth_refresh_token_expires_days, 1)
    expires_delta = timedelta(days=expires_days)
    expire = datetime.now(UTC) + expires_delta

    payload = {
        "sub": user_id,
        "email": email,
        "iss": settings.auth_issuer,
        "jti": uuid.uuid4().hex,
        "ver": token_version,
        "typ": "refresh",
        "iat": datetime.now(UTC),
        "exp": expire,
    }

    token = jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)
    return token, int(expires_delta.total_seconds())


def revoke_user_tokens(db: Session, user: User) -> None:
    """Invalida todos los tokens activos del usuario incrementando token_version."""
    user.token_version += 1
    db.add(user)
    db.commit()


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[settings.auth_algorithm],
            issuer=settings.auth_issuer,
            options={"require": ["exp", "sub", "iat", "ver"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token vencido. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError as exc:
        logger.warning("Token inválido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o vencido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def decode_refresh_token(token: str) -> dict:
    """Valida un refresh token: firma, tipo y claims obligatorios.

    No exige vigencia del access token asociado; el refresh token tiene
    su propia expiración de largo plazo.
    """
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[settings.auth_algorithm],
            issuer=settings.auth_issuer,
            options={"require": ["exp", "sub", "iat", "ver", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tu sesión finalizó por inactividad. Inicia sesión nuevamente.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        logger.warning("Refresh token inválido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida. Inicia sesión nuevamente.",
        ) from exc

    if payload.get("typ") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de renovación no válido.",
        )

    return payload


def _load_user_for_refresh(db: Session, payload: dict) -> User:
    return load_user_for_refresh(db, payload)


def load_user_for_refresh(db: Session, payload: dict) -> User:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida.",
        )

    user = db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autorizado o inactivo.",
        )

    token_version = payload.get("ver")
    if not isinstance(token_version, int) or token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión revocada. Inicia sesión nuevamente.",
        )

    return user


def issue_session_tokens(user: User) -> tuple[str, int, str, int]:
    """Genera el par access + refresh para una sesión persistente."""
    access_token, expires_in = create_access_token(
        user.id, user.email, token_version=user.token_version
    )
    refresh_token, refresh_expires_in = create_refresh_token(
        user.id, user.email, token_version=user.token_version
    )
    return access_token, expires_in, refresh_token, refresh_expires_in


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autorizado o inactivo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_version = payload.get("ver")
    if not isinstance(token_version, int) or token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión revocada. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Como get_current_user pero devuelve None si no hay sesión válida.

    Usado por /refresh para aceptar también renovación vía refresh token.
    """
    if not token:
        return None
    try:
        return get_current_user(token=token, db=db)
    except HTTPException:
        return None
