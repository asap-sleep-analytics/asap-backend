from pathlib import Path
from typing import Generator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from main import app


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    test_db_file = tmp_path / "waitlist_test.db"
    test_database_url = f"sqlite:///{test_db_file}"

    engine = create_engine(test_database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


def test_create_waitlist_lead(client: TestClient) -> None:

    payload = {
        "name": "Alejandro Test",
        "email": "alejandro@example.com",
        "device": "android",
        "source": "landing-page",
    }

    response = client.post("/api/leads", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["lead"]["email"] == payload["email"]
    assert body["lead"]["status"] == "pending"
    assert body["confirmation_url_preview"]


def test_confirm_waitlist_lead(client: TestClient) -> None:
    payload = {
        "name": "Daniela Test",
        "email": "daniela@example.com",
        "device": "ios",
        "source": "landing-page",
    }

    create_response = client.post("/api/leads", json=payload)
    confirmation_preview = create_response.json()["confirmation_url_preview"]

    parsed = urlparse(confirmation_preview)
    token = parse_qs(parsed.query)["token"][0]

    confirm_response = client.get(f"/api/leads/confirm?token={token}")

    assert confirm_response.status_code == 200
    confirm_body = confirm_response.json()
    assert confirm_body["ok"] is True
    assert confirm_body["lead"]["status"] == "confirmed"


def test_list_waitlist_leads(client: TestClient) -> None:
    client.post(
        "/api/leads",
        json={
            "name": "Dario Test",
            "email": "dario@example.com",
            "device": "both",
            "source": "landing-page",
        },
    )

    response = client.get("/api/leads?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["lead_id"]


def test_resend_confirmation_rotates_token(client: TestClient) -> None:
    create_response = client.post(
        "/api/leads",
        json={
            "name": "Resend Test",
            "email": "resend@example.com",
            "device": "ios",
            "source": "landing-page",
        },
    )

    first_preview = create_response.json()["confirmation_url_preview"]
    first_token = parse_qs(urlparse(first_preview).query)["token"][0]

    resend_response = client.post(
        "/api/leads/resend-confirmation",
        json={"email": "resend@example.com"},
    )
    assert resend_response.status_code == 200
    resend_body = resend_response.json()
    second_preview = resend_body["confirmation_url_preview"]
    second_token = parse_qs(urlparse(second_preview).query)["token"][0]

    assert first_token != second_token
    assert resend_body["lead"]["status"] == "pending"

    stale_confirmation = client.get(f"/api/leads/confirm?token={first_token}")
    assert stale_confirmation.status_code == 400

    fresh_confirmation = client.get(f"/api/leads/confirm?token={second_token}")
    assert fresh_confirmation.status_code == 200


def test_resend_confirmation_nonexistent_email(client: TestClient) -> None:
    response = client.post(
        "/api/leads/resend-confirmation",
        json={"email": "notfound@example.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lead"] is None
    assert "Si este correo existe" in body["message"]
