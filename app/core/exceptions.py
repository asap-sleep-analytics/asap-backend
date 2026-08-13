from __future__ import annotations

from fastapi import status


class AppError(Exception):
    """Error de dominio con status code HTTP asociado.

    Las capas de servicio lanzan subclases concretas; los handlers globales
    las convierten en respuestas JSON sin que las rutas necesiten traducir
    mensajes por texto.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Error interno del servidor."

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Recurso no encontrado."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Conflicto con el estado actual del recurso."


class ValidationError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Solicitud inválida."


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Credenciales inválidas."


class SessionNotFoundError(NotFoundError):
    detail = "Sesión no encontrada."


class SessionAlreadyFinishedError(ConflictError):
    detail = "La sesión ya fue finalizada."


class InvalidSessionTimeError(ValidationError):
    detail = "La hora final debe ser posterior a la hora de inicio."


class FeedbackNotFoundError(NotFoundError):
    detail = "Feedback no encontrado."


class LeadNotFoundError(NotFoundError):
    detail = "Lead no encontrado."


class DuplicateUserError(ConflictError):
    detail = "El correo ya está registrado."


class InvalidCredentialsError(UnauthorizedError):
    detail = "Correo o contraseña inválidos."
