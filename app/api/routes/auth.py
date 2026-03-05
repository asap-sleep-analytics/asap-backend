from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.models.auth import AuthTokenResponse, UserLoginRequest, UserPublic, UserRegisterRequest
from app.services.auth import get_profile, login_user, register_user

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])


@router.post("/registro", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register_user_endpoint(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    try:
        return register_user(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=AuthTokenResponse)
def login_user_endpoint(
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    try:
        return login_user(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/perfil", response_model=UserPublic)
def profile_endpoint(current_user: User = Depends(get_current_user)) -> UserPublic:
    return get_profile(current_user)
