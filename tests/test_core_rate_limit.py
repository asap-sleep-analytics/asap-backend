import os
from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.rate_limit import InMemoryRateLimiter, rate_limit_dependency, reset_rate_limiter_for_tests


@pytest.fixture(autouse=True)
def _limpiar_limiter() -> Generator[None, None, None]:
    reset_rate_limiter_for_tests()
    yield
    reset_rate_limiter_for_tests()


@pytest.fixture()
def _rate_limit_habilitado() -> Generator[None, None, None]:
    with patch("app.core.rate_limit._rate_limit_disabled", return_value=False):
        yield


def test_permite_solicitudes_dentro_del_limite(_rate_limit_habilitado) -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        limiter.check("clave:test", max_requests=5, window_seconds=60)


def test_excede_el_limite_lanza_429(_rate_limit_habilitado) -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        limiter.check("clave:test", max_requests=5, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("clave:test", max_requests=5, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_limite_por_clave_independiente(_rate_limit_habilitado) -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        limiter.check("a:test", max_requests=5, window_seconds=60)

    # Otra clave no debe verse afectada
    limiter.check("b:test", max_requests=5, window_seconds=60)


def test_ventana_rota_despeja_contador(_rate_limit_habilitado) -> None:
    limiter = InMemoryRateLimiter()

    with patch("app.core.rate_limit.time.monotonic") as mock_time:
        mock_time.return_value = 100.0
        for _ in range(5):
            limiter.check("clave:test", max_requests=5, window_seconds=60)
        with pytest.raises(HTTPException):
            limiter.check("clave:test", max_requests=5, window_seconds=60)

        # 60s después la ventana se reinicia
        mock_time.return_value = 161.0
        limiter.check("clave:test", max_requests=5, window_seconds=60)


def test_reset_limpia_todos_los_contadores(_rate_limit_habilitado) -> None:
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        limiter.check("clave:test", max_requests=5, window_seconds=60)

    limiter.reset()
    limiter.check("clave:test", max_requests=5, window_seconds=60)


def test_rate_limit_dependency_usa_ip_del_request(_rate_limit_habilitado) -> None:
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        url = type("URL", (), {"path": "/api/v1/auth/login"})()
        client = FakeClient()

    dependency = rate_limit_dependency(max_requests=2, window_seconds=60)
    dependency(FakeRequest())
    dependency(FakeRequest())

    with pytest.raises(HTTPException) as exc_info:
        dependency(FakeRequest())
    assert exc_info.value.status_code == 429


def test_rate_limit_dependency_sin_client_usa_unknown(_rate_limit_habilitado) -> None:
    class FakeRequest:
        url = type("URL", (), {"path": "/x"})()
        client = None

    dependency = rate_limit_dependency(max_requests=1, window_seconds=60)
    dependency(FakeRequest())
    with pytest.raises(HTTPException):
        dependency(FakeRequest())


def test_deshabilitado_en_desarrollo() -> None:
    with patch.dict(os.environ, {"APP_ENV": "development", "DISABLE_RATE_LIMIT": "1"}, clear=False):
        limiter = InMemoryRateLimiter()
        for _ in range(100):
            limiter.check("clave:test", max_requests=5, window_seconds=60)


def test_no_deshabilitado_en_produccion() -> None:
    with patch.dict(os.environ, {"APP_ENV": "production", "DISABLE_RATE_LIMIT": "1"}, clear=False):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            limiter.check("clave:test", max_requests=5, window_seconds=60)
        with pytest.raises(HTTPException):
            limiter.check("clave:test", max_requests=5, window_seconds=60)
