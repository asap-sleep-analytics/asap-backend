from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from main import app


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    test_db_file = tmp_path / "sleep_test.db"
    test_database_url = f"sqlite:///{test_db_file}"

    engine = create_engine(test_database_url, connect_args={"check_same_thread": False})
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/registro",
        json={
            "nombre_completo": "Sleep Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_calibracion_ruido_alto(client: TestClient) -> None:
    response = client.post(
        "/api/sleep/calibracion",
        json={"ambient_noise_level": 62},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["nivel_ruido"] == "alto"


def test_iniciar_y_finalizar_sesion(client: TestClient) -> None:
    token = _register(client, "sleep.session@example.com")

    start = client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 36},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "snore_count": 8,
            "apnea_events": 2,
            "avg_oxygen": 96,
            "ambient_noise_level": 40,
        },
    )

    assert finish.status_code == 200
    body = finish.json()
    assert body["sesion"]["sleep_score"] is not None
    assert isinstance(body["sesion"]["continuidad"], list)
    assert len(body["sesion"]["continuidad"]) >= 1


def test_listar_sesiones(client: TestClient) -> None:
    token = _register(client, "sleep.list@example.com")

    client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 32},
    )

    response = client.get(
        "/api/sleep/sesiones?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
