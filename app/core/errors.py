import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


ERROR_RESPONSES = {
    "validation_error": "VALIDATION_ERROR",
    "internal_error": "INTERNAL_ERROR",
    "not_found": "NOT_FOUND",
}


def register_error_handlers(app) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        logger.info(
            "HTTPException %s %s",
            exc.status_code,
            exc.detail,
            extra=_request_extra(_),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "detail": exc.detail,
                "code": _status_code_to_code(exc.status_code),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(part) for part in err.get("loc", []))
            errors.append(f"{loc}: {err.get('msg', 'error desconocido')}")
        detail = "; ".join(errors) if errors else "Error de validación"
        logger.warning(
            "Validation error: %s",
            detail,
            extra=_request_extra(_),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": True, "detail": detail, "code": ERROR_RESPONSES["validation_error"]},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error on %s %s",
            _.method,
            _.url.path,
            extra=_request_extra(_),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "detail": "Error interno del servidor.",
                "code": ERROR_RESPONSES["internal_error"],
            },
        )


def _request_extra(request: Request) -> dict:
    request_id = getattr(request.state, "request_id", None)
    return {"request_id": request_id} if request_id else {}


def _status_code_to_code(status_code: int) -> str:
    if status_code == 404:
        return ERROR_RESPONSES["not_found"]
    if status_code == 422:
        return ERROR_RESPONSES["validation_error"]
    if status_code >= 500:
        return ERROR_RESPONSES["internal_error"]
    return f"HTTP_{status_code}"
