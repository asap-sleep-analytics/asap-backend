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
    test_db_file = tmp_path / "auth_test.db"
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


def test_registro_exitoso(client: TestClient) -> None:
    response = client.post(
        "/api/auth/registro",
        json={
            "nombre_completo": "Alejandro Usuario",
            "email": "alejandro.auth@example.com",
            "password": "ClaveSegura123",
            "ronca_habitualmente": True,
            "cansancio_diurno": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["access_token"]
    assert body["usuario"]["email"] == "alejandro.auth@example.com"
    assert body["usuario"]["ronca_habitualmente"] is True


def test_registro_duplicado(client: TestClient) -> None:
    payload = {
        "nombre_completo": "Cuenta Duplicada",
        "email": "duplicado@example.com",
        "password": "ClaveSegura123",
        "ronca_habitualmente": False,
        "cansancio_diurno": False,
        "acepta_consentimiento_datos": True,
        "acepta_disclaimer_medico": True,
    }

    first = client.post("/api/auth/registro", json=payload)
    second = client.post("/api/auth/registro", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_login_y_perfil(client: TestClient) -> None:
    client.post(
        "/api/auth/registro",
        json={
            "nombre_completo": "Perfil Usuario",
            "email": "perfil@example.com",
            "password": "ClaveSegura123",
            "ronca_habitualmente": False,
            "cansancio_diurno": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )

    login = client.post(
        "/api/auth/login",
        json={
            "email": "perfil@example.com",
            "password": "ClaveSegura123",
        },
    )

    assert login.status_code == 200
    token = login.json()["access_token"]

    perfil = client.get(
        "/api/auth/perfil",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert perfil.status_code == 200
    assert perfil.json()["email"] == "perfil@example.com"


def test_login_invalido(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "noexiste@example.com",
            "password": "ClaveSegura123",
        },
    )

    assert response.status_code == 401


def test_registro_rechazado_sin_consentimiento(client: TestClient) -> None:
    response = client.post(
        "/api/auth/registro",
        json={
            "nombre_completo": "Sin Consentimiento",
            "email": "sin.consentimiento@example.com",
            "password": "ClaveSegura123",
            "acepta_consentimiento_datos": False,
            "acepta_disclaimer_medico": True,
        },
    )

    assert response.status_code == 400
