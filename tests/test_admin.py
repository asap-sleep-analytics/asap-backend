from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from main import app


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    test_db_file = tmp_path / "admin_test.db"
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
            "nombre_completo": "Dataset Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_export_dataset_json_y_csv(client: TestClient) -> None:
    token = _register(client, "dataset.export@example.com")

    start = client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 33},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 3, "apnea_events": 1, "avg_oxygen": 95},
    )
    assert finish.status_code == 200

    feedback = client.post(
        f"/api/sleep/sesiones/{session_id}/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "calificacion_descanso": 3,
            "desperto_cansado": True,
            "comentario": "Necesito ajustar rutina.",
        },
    )
    assert feedback.status_code == 200

    export_json = client.get(
        "/api/admin/dataset/export?format=json",
        headers={"X-Admin-Export-Key": settings.admin_dataset_export_key},
    )

    assert export_json.status_code == 200
    body = export_json.json()
    assert body["ok"] is True
    assert body["total"] >= 1
    first_row = body["rows"][0]
    assert "session_id" in first_row
    assert "feedback_sleep_rating" in first_row

    export_csv = client.get(
        "/api/admin/dataset/export?format=csv",
        headers={"X-Admin-Export-Key": settings.admin_dataset_export_key},
    )

    assert export_csv.status_code == 200
    assert "text/csv" in export_csv.headers.get("content-type", "")
    assert "session_id" in export_csv.text


def test_export_dataset_requiere_clave_admin(client: TestClient) -> None:
    response = client.get("/api/admin/dataset/export?format=json")
    assert response.status_code == 403
