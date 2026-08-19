from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit_dependency
from app.core.security import create_access_token, get_current_user, revoke_user_tokens
from app.db.models import User
from app.db.session import get_db
from app.models.auth import (
    AuthTokenResponse,
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
    current_user: User = Depends(get_current_user),
) -> AuthTokenResponse:
    token, expires_in = create_access_token(current_user.id, current_user.email, token_version=current_user.token_version)
    return AuthTokenResponse(
        mensaje="Token renovado exitosamente.",
        access_token=token,
        expires_in=expires_in,
        usuario=UserPublic(
            user_id=current_user.id,
            nombre_completo=current_user.full_name,
            email=current_user.email,
            activo=current_user.is_active,
            metodo_ingreso=current_user.auth_provider,
            ronca_habitualmente=current_user.ronca_habitualmente,
            cansancio_diurno=current_user.cansancio_diurno,
            creado_en=current_user.created_at,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    revoke_user_tokens(db=db, user=current_user)


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
