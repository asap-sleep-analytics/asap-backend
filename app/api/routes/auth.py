from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit_dependency
from app.core.security import (
    decode_refresh_token,
    get_current_user,
    get_current_user_optional,
    issue_session_tokens,
    load_user_for_refresh,
    revoke_user_tokens,
)
from app.db.models import User
from app.db.session import get_db
from app.models.auth import (
    AuthTokenResponse,
    EmailVerificationSendResponse,
    ForgotPasswordRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SocialLoginRequest,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from app.services.auth import (
    LegalAcceptanceError,
    delete_user_data,
    get_profile,
    login_social,
    login_user,
    register_user,
    request_password_reset,
    reset_password,
    send_email_verification,
    verify_email,
)

router = APIRouter(prefix="/api/v1/auth", tags=["autenticacion"])


@router.post("/registro", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register_user_endpoint(
    payload: Annotated[UserRegisterRequest, Body()],
    _: None = Depends(rate_limit_dependency(max_requests=3, window_seconds=60)),
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    try:
        return register_user(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/login", response_model=AuthTokenResponse)
def login_user_endpoint(
    payload: Annotated[UserLoginRequest, Body()],
    _: None = Depends(rate_limit_dependency(max_requests=5, window_seconds=60)),
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    try:
        return login_user(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/social/login", response_model=AuthTokenResponse)
def social_login_endpoint(
    payload: Annotated[SocialLoginRequest, Body()],
    _: None = Depends(rate_limit_dependency(max_requests=5, window_seconds=60)),
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    try:
        return login_social(db=db, payload=payload)
    except LegalAcceptanceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh_token_endpoint(
    payload: Annotated[RefreshTokenRequest | None, Body()] = None,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    """Renueva la sesión de forma persistente.

    Prioriza el refresh token de larga duración enviado en el body (permite
    renovar aunque el access token haya expirado, como en IG/FB/X). Si no se
    envía, acepta un access token vigente vía header Authorization.
    En ambos casos rota el refresh token entregando uno nuevo.
    """
    if payload and payload.refresh_token:
        claims = decode_refresh_token(payload.refresh_token)
        user = load_user_for_refresh(db, claims)
    elif current_user is not None:
        user = current_user
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida. Inicia sesión nuevamente.",
        )

    access_token, expires_in, refresh_token, _ = issue_session_tokens(user)
    return AuthTokenResponse(
        mensaje="Token renovado exitosamente.",
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_token,
        usuario=get_profile(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    revoke_user_tokens(db=db, user=current_user)


@router.post("/email/enviar-verificacion", response_model=EmailVerificationSendResponse)
def send_email_verification_endpoint(
    current_user: User = Depends(get_current_user),
    _: None = Depends(rate_limit_dependency(max_requests=3, window_seconds=60)),
    db: Session = Depends(get_db),
) -> EmailVerificationSendResponse:
    try:
        return send_email_verification(db=db, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/email/verificar", response_model=MessageResponse)
def verify_email_endpoint(
    token: Annotated[str, Query(min_length=10, max_length=128)],
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        return verify_email(db=db, token=token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/password/olvidada", response_model=MessageResponse)
def forgot_password_endpoint(
    payload: Annotated[ForgotPasswordRequest, Body()],
    _: None = Depends(rate_limit_dependency(max_requests=5, window_seconds=3600)),
    db: Session = Depends(get_db),
) -> MessageResponse:
    return request_password_reset(db=db, email=payload.email)


@router.post("/password/restablecer", response_model=MessageResponse)
def reset_password_endpoint(
    payload: Annotated[ResetPasswordRequest, Body()],
    _: None = Depends(rate_limit_dependency(max_requests=5, window_seconds=600)),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        return reset_password(db=db, token=payload.token, nueva_password=payload.nueva_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/perfil", response_model=UserPublic)
def profile_endpoint(current_user: User = Depends(get_current_user)) -> UserPublic:
    return get_profile(current_user)


@router.delete("/cuenta", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_endpoint(
    current_user: User = Depends(get_current_user),
    _: None = Depends(rate_limit_dependency(max_requests=3, window_seconds=60)),
    db: Session = Depends(get_db),
) -> None:
    delete_user_data(db=db, user=current_user)
