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
