from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    nombre_completo: str = Field(..., min_length=2, max_length=120)
    email: str = Field(
        ...,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Correo del usuario.",
    )
    password: str = Field(..., min_length=8, max_length=128)
    ronca_habitualmente: bool = Field(default=False)
    cansancio_diurno: bool = Field(default=False)
    acepta_terminos_condiciones: bool = Field(
        default=False,
        description="Aceptación de los términos y condiciones de uso de la app.",
    )
    acepta_consentimiento_datos: bool = Field(
        default=False,
        description="Consentimiento informado para tratamiento de datos (Ley 1581).",
    )
    acepta_disclaimer_medico: bool = Field(
        default=False,
        description="Confirmación de que la app no reemplaza diagnóstico clínico profesional.",
    )


class UserLoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)


class SocialLoginRequest(BaseModel):
    provider: Literal["google", "apple"]
    id_token: str = Field(..., min_length=1, max_length=4096)
    nombre_completo: str | None = Field(default=None, min_length=2, max_length=120)
    ronca_habitualmente: bool = Field(default=False)
    cansancio_diurno: bool = Field(default=False)
    acepta_terminos_condiciones: bool = Field(
        default=False,
        description="Aceptación de los términos y condiciones (requerida al crear la cuenta).",
    )
    acepta_consentimiento_datos: bool = Field(
        default=False,
        description="Consentimiento informado para tratamiento de datos (Ley 1581).",
    )
    acepta_disclaimer_medico: bool = Field(
        default=False,
        description="Confirmación de que la app no reemplaza diagnóstico clínico profesional.",
    )


class UserPublic(BaseModel):
    user_id: str
    nombre_completo: str
    email: str
    activo: bool
    metodo_ingreso: str
    ronca_habitualmente: bool
    cansancio_diurno: bool
    creado_en: datetime
    email_verificado: bool = Field(default=False)


class AuthTokenResponse(BaseModel):
    ok: bool = True
    mensaje: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UserPublic


class MessageResponse(BaseModel):
    ok: bool = True
    mensaje: str


class EmailVerificationSendResponse(BaseModel):
    ok: bool = True
    mensaje: str
    verificacion_url_preview: str | None = Field(
        default=None,
        description="Solo disponible cuando SMTP no está configurado (desarrollo local).",
    )


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=128)
    nueva_password: str = Field(..., min_length=8, max_length=128)
