import secrets
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Lead, SleepDetectionLog, SleepSession, User, UserFeedback
from app.models.auth import (
    AuthTokenResponse,
    SocialLoginRequest,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from app.services.audio_processor import cleanup_session_fragments
from app.services.social_auth import SocialAuthError, verify_id_token

_FRAGMENT_ROOT = Path(settings.sleep_fragment_root)


class LegalAcceptanceError(ValueError):
    """Faltan aceptaciones legales requeridas para crear la cuenta."""


def _to_public_user(user: User) -> UserPublic:
    return UserPublic(
        user_id=user.id,
        nombre_completo=user.full_name,
        email=user.email,
        activo=user.is_active,
        metodo_ingreso=user.auth_provider,
        ronca_habitualmente=user.ronca_habitualmente,
        cansancio_diurno=user.cansancio_diurno,
        creado_en=user.created_at,
    )


def _issue_auth_response(db: Session, user: User, mensaje: str) -> AuthTokenResponse:
    token, expires_in = create_access_token(user.id, user.email, token_version=user.token_version)
    return AuthTokenResponse(
        mensaje=mensaje,
        access_token=token,
        expires_in=expires_in,
        usuario=_to_public_user(user),
    )


def _validate_legal_acceptance(payload: UserRegisterRequest | SocialLoginRequest) -> None:
    if not payload.acepta_terminos_condiciones:
        raise LegalAcceptanceError("Debes aceptar los términos y condiciones para crear la cuenta.")
    if not payload.acepta_consentimiento_datos:
        raise LegalAcceptanceError("Debes aceptar el consentimiento informado (Ley 1581) para crear la cuenta.")
    if not payload.acepta_disclaimer_medico:
        raise LegalAcceptanceError("Debes aceptar el disclaimer médico para continuar.")


def register_user(db: Session, payload: UserRegisterRequest) -> AuthTokenResponse:
    _validate_legal_acceptance(payload)

    normalized_email = payload.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise ValueError("No se pudo completar el registro. Revisa los datos e intenta de nuevo.")

    now = datetime.now(UTC)

    user = User(
        full_name=payload.nombre_completo.strip(),
        email=normalized_email,
        password_hash=hash_password(payload.password),
        is_active=True,
        share_token=secrets.token_urlsafe(24),
        auth_provider="local",
        ronca_habitualmente=payload.ronca_habitualmente,
        cansancio_diurno=payload.cansancio_diurno,
        terms_accepted_at=now,
        informed_consent_at=now,
        medical_disclaimer_accepted_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_auth_response(db, user, mensaje="Registro exitoso.")


def login_user(db: Session, payload: UserLoginRequest) -> AuthTokenResponse:
    normalized_email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise ValueError("Credenciales inválidas.")

    if not user.is_active:
        raise ValueError("La cuenta está desactivada.")

    return _issue_auth_response(db, user, mensaje="Inicio de sesión exitoso.")


def login_social(db: Session, payload: SocialLoginRequest) -> AuthTokenResponse:
    try:
        identity = verify_id_token(provider=payload.provider, id_token=payload.id_token)
    except SocialAuthError as exc:
        raise ValueError(str(exc)) from exc

    user = db.scalar(
        select(User).where(
            User.auth_provider == identity.provider,
            User.social_subject == identity.subject,
        )
    )

    if user is None and identity.email:
        user = db.scalar(select(User).where(User.email == identity.email))

    if user is None:
        if not identity.email:
            raise ValueError("El proveedor no proporcionó un correo para crear la cuenta.")
        if not identity.email_verified:
            raise ValueError("El correo de la cuenta aún no está verificado por el proveedor.")

        _validate_legal_acceptance(payload)

        now = datetime.now(UTC)
        user = User(
            full_name=(payload.nombre_completo or identity.full_name or "Usuario A.S.A.P.").strip()[:120],
            email=identity.email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            share_token=secrets.token_urlsafe(24),
            auth_provider=identity.provider,
            social_subject=identity.subject,
            ronca_habitualmente=payload.ronca_habitualmente,
            cansancio_diurno=payload.cansancio_diurno,
            terms_accepted_at=now,
            informed_consent_at=now,
            medical_disclaimer_accepted_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return _issue_auth_response(db, user, mensaje=f"Cuenta creada con {identity.provider}. Registro exitoso.")

    if not user.is_active:
        raise ValueError("La cuenta está desactivada.")

    if user.auth_provider != identity.provider and not user.social_subject:
        user.auth_provider = identity.provider
        user.social_subject = identity.subject
        db.add(user)
        db.commit()
        db.refresh(user)

    return _issue_auth_response(db, user, mensaje=f"Inicio de sesión con {identity.provider} exitoso.")


def get_profile(user: User) -> UserPublic:
    return _to_public_user(user)


def delete_user_data(db: Session, user: User) -> None:
    """Elimina la cuenta y todos los datos de salud del usuario en la nube (Ley 1581)."""
    session_ids = list(db.scalars(select(SleepSession.id).where(SleepSession.user_id == user.id)))

    if session_ids:
        db.execute(delete(SleepDetectionLog).where(SleepDetectionLog.session_id.in_(session_ids)))
    db.execute(delete(UserFeedback).where(UserFeedback.user_id == user.id))
    if session_ids:
        db.execute(delete(SleepSession).where(SleepSession.id.in_(session_ids)))
    db.execute(delete(Lead).where(Lead.email == user.email))
    db.delete(user)
    db.commit()

    for session_id in session_ids:
        cleanup_session_fragments(session_id=session_id, fragment_root=_FRAGMENT_ROOT)
