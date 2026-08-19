import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, revoke_user_tokens, verify_password
from app.db.models import Lead, SleepDetectionLog, SleepSession, User, UserFeedback
from app.models.auth import (
    AuthTokenResponse,
    EmailVerificationSendResponse,
    MessageResponse,
    SocialLoginRequest,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from app.services.audio_processor import cleanup_session_fragments
from app.services.email import send_email_verification_email, send_password_reset_email
from app.services.social_auth import SocialAuthError, verify_id_token

_FRAGMENT_ROOT = Path(settings.sleep_fragment_root)


class LegalAcceptanceError(ValueError):
    """Faltan aceptaciones legales requeridas para crear la cuenta."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _build_action_url(base_url: str, token: str) -> str:
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}token={token}"


def _mark_email_verified(user: User) -> None:
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    user.password_reset_token_hash = None
    user.password_reset_token_expires_at = None


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
        email_verificado=user.email_verified_at is not None,
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

    _issue_email_verify_token(user, db=db, send=True)

    return _issue_auth_response(db, user, mensaje="Registro exitoso.")


def _issue_email_verify_token(user: User, db: Session, send: bool) -> tuple[bool, str]:
    """Genera un token de verificación de un solo uso y, si el SMTP está listo, envía el correo."""
    token = secrets.token_urlsafe(32)
    user.email_verify_token_hash = _hash_token(token)
    user.email_verify_token_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.auth_email_verify_token_ttl_minutes
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    verification_url = _build_action_url(settings.auth_email_verify_url_base, token)
    if not send:
        return False, verification_url
    smtp_ok = send_email_verification_email(
        name=user.full_name,
        email=user.email,
        verification_url=verification_url,
    )
    return smtp_ok, verification_url


def send_email_verification(db: Session, user: User) -> EmailVerificationSendResponse:
    if user.email_verified_at is not None:
        return EmailVerificationSendResponse(mensaje="Tu correo ya está verificado.")
    if not user.is_active:
        raise ValueError("La cuenta está desactivada.")

    smtp_ok, verification_url = _issue_email_verify_token(user, db=db, send=True)
    if smtp_ok:
        return EmailVerificationSendResponse(
            mensaje="Revisa tu correo para completar la verificación de tu cuenta."
        )
    return EmailVerificationSendResponse(
        mensaje="Revisa tu correo para completar la verificación de tu cuenta (SMTP no configurado).",
        verificacion_url_preview=verification_url,
    )


def verify_email(db: Session, token: str) -> MessageResponse:
    token_hash = _hash_token(token)
    user = db.scalar(select(User).where(User.email_verify_token_hash == token_hash))
    if not user:
        raise ValueError("El enlace de verificación no es válido.")

    if user.email_verified_at is not None:
        return MessageResponse(mensaje="Tu correo ya estaba verificado.")

    now = datetime.now(UTC)
    expires_at = user.email_verify_token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if not expires_at or expires_at < now:
        raise ValueError("El enlace de verificación expiró. Solicita uno nuevo desde la app.")

    _mark_email_verified(user)
    db.add(user)
    db.commit()

    return MessageResponse(mensaje="Correo verificado correctamente. Bienvenido a A.S.A.P.")


def request_password_reset(db: Session, email: str) -> MessageResponse:
    """Solicita el restablecimiento de contraseña sin revelar si el correo existe."""
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))

    if not user or not user.is_active:
        return MessageResponse(
            mensaje="Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."
        )

    token = secrets.token_urlsafe(32)
    user.password_reset_token_hash = _hash_token(token)
    user.password_reset_token_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.auth_password_reset_token_ttl_minutes
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    reset_url = _build_action_url(settings.auth_password_reset_url_base, token)
    send_password_reset_email(name=user.full_name, email=user.email, reset_url=reset_url)

    return MessageResponse(
        mensaje="Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."
    )


def reset_password(db: Session, token: str, nueva_password: str) -> MessageResponse:
    token_hash = _hash_token(token)
    user = db.scalar(select(User).where(User.password_reset_token_hash == token_hash))
    if not user:
        raise ValueError("El enlace para restablecer la contraseña no es válido.")

    if not user.is_active:
        raise ValueError("La cuenta está desactivada.")

    now = datetime.now(UTC)
    expires_at = user.password_reset_token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if not expires_at or expires_at < now:
        raise ValueError(
            "El enlace para restablecer la contraseña expiró. Solicita uno nuevo."
        )

    user.password_hash = hash_password(nueva_password)
    user.password_reset_token_hash = None
    user.password_reset_token_expires_at = None
    db.add(user)
    db.commit()
    db.refresh(user)

    revoke_user_tokens(db, user)

    return MessageResponse(mensaje="Contraseña restablecida. Inicia sesión con tu nueva contraseña.")


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
            email_verified_at=now if identity.email_verified else None,
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

    if identity.email_verified and user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
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
