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
    test_db_file = tmp_path / "dashboard_test.db"
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
            "nombre_completo": "Usuario Dashboard",
            "email": email,
            "password": "ClaveSegura123",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_dashboard_resumen_auth_required(client: TestClient) -> None:
    response = client.get("/api/dashboard/resumen")
    assert response.status_code == 401


def test_dashboard_resumen_ok(client: TestClient) -> None:
    token = _register(client, "dashboard@example.com")

    client.post(
        "/api/leads",
        json={
            "name": "Lead Uno",
            "email": "leaduno@example.com",
            "device": "ios",
            "source": "landing-page",
        },
    )
    client.post(
        "/api/leads",
        json={
            "name": "Lead Dos",
            "email": "leaddos@example.com",
            "device": "android",
            "source": "landing-page",
        },
    )

    response = client.get(
        "/api/dashboard/resumen",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["usuario"]["email"] == "dashboard@example.com"
    assert body["metricas"]["total_usuarios"] >= 1
    assert body["metricas"]["total_leads"] >= 2
    assert len(body["sugerencias"]) >= 1
