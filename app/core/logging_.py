import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        logger = logging.getLogger("app.access")
        extra = {"request_id": request_id}

        logger.info(
            "IN  %s %s",
            request.method,
            request.url.path,
            extra=extra,
        )

        start = datetime.now(UTC)
        response: Response = await call_next(request)
        elapsed = (datetime.now(UTC) - start).total_seconds()

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "OUT %s %s %d %.4fs",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            extra=extra,
        )

        return response
