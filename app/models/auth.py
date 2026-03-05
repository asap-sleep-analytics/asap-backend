from datetime import datetime

from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    nombre_completo: str = Field(..., min_length=2, max_length=120)
    email: str = Field(
        ...,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Correo del usuario.",
    )
    password: str = Field(..., min_length=8, max_length=128)


class UserLoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)


class UserPublic(BaseModel):
    user_id: str
    nombre_completo: str
    email: str
    activo: bool
    creado_en: datetime


class AuthTokenResponse(BaseModel):
    ok: bool = True
    mensaje: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UserPublic
