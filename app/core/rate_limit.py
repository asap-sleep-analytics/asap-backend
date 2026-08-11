import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


def _rate_limit_disabled() -> bool:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env in {"prod", "production"}:
        return False
    return os.getenv("DISABLE_RATE_LIMIT", "").lower() in {"1", "true", "yes"}


class InMemoryRateLimiter:
    """Rate limiter en memoria (un solo proceso/worker).

    Limitación conocida: si la API corre con multiples workers/replicas,
    cada worker mantiene su propio contador, por lo que el límite efectivo
    es mayor al configurado. Para despliegues multi-worker se debe
    sustituir por un almacen compartido (Redis, etc.).
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        if _rate_limit_disabled():
            return
        now = time.monotonic()
        window_start = now - window_seconds

        timestamps = self._windows[key]
        timestamps[:] = [t for t in timestamps if t > window_start]

        if len(timestamps) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas solicitudes. Intenta de nuevo más tarde.",
            )

        timestamps.append(now)

    def reset(self) -> None:
        self._windows.clear()


_rate_limiter = InMemoryRateLimiter()


def rate_limit_dependency(max_requests: int, window_seconds: int):
    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client_ip}"
        _rate_limiter.check(key, max_requests, window_seconds)

    return dependency


def reset_rate_limiter_for_tests() -> None:
    _rate_limiter.reset()
