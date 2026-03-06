import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.models.auth import AuthTokenResponse, UserLoginRequest, UserPublic, UserRegisterRequest


def _to_public_user(user: User) -> UserPublic:
    return UserPublic(
        user_id=user.id,
        nombre_completo=user.full_name,
        email=user.email,
        activo=user.is_active,
        ronca_habitualmente=user.ronca_habitualmente,
        cansancio_diurno=user.cansancio_diurno,
        creado_en=user.created_at,
    )


def register_user(db: Session, payload: UserRegisterRequest) -> AuthTokenResponse:
    if not payload.acepta_consentimiento_datos:
        raise ValueError("Debes aceptar el consentimiento informado (Ley 1581) para crear la cuenta.")

    if not payload.acepta_disclaimer_medico:
        raise ValueError("Debes aceptar el disclaimer médico para continuar.")

    normalized_email = payload.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise ValueError("Ya existe una cuenta registrada con este correo.")

    now = datetime.now(timezone.utc)

    user = User(
        full_name=payload.nombre_completo.strip(),
        email=normalized_email,
        password_hash=hash_password(payload.password),
        is_active=True,
        share_token=secrets.token_urlsafe(24),
        ronca_habitualmente=payload.ronca_habitualmente,
        cansancio_diurno=payload.cansancio_diurno,
        informed_consent_at=now,
        medical_disclaimer_accepted_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token, expires_in = create_access_token(user.id, user.email)
    return AuthTokenResponse(
        mensaje="Registro exitoso.",
        access_token=token,
        expires_in=expires_in,
        usuario=_to_public_user(user),
    )


def login_user(db: Session, payload: UserLoginRequest) -> AuthTokenResponse:
    normalized_email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise ValueError("Credenciales inválidas.")

    if not user.is_active:
        raise ValueError("La cuenta está desactivada.")

    token, expires_in = create_access_token(user.id, user.email)
    return AuthTokenResponse(
        mensaje="Inicio de sesión exitoso.",
        access_token=token,
        expires_in=expires_in,
        usuario=_to_public_user(user),
    )


def get_profile(user: User) -> UserPublic:
    return _to_public_user(user)
