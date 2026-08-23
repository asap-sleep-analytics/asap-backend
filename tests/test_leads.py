from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Test User",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_create_waitlist_lead(client: TestClient) -> None:

    payload = {
        "name": "Alejandro Test",
        "email": "alejandro@example.com",
        "device": "android",
        "source": "landing-page",
    }

    response = client.post("/api/v1/leads", json=payload)

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

    create_response = client.post("/api/v1/leads", json=payload)
    confirmation_preview = create_response.json()["confirmation_url_preview"]

    parsed = urlparse(confirmation_preview)
    token = parse_qs(parsed.query)["token"][0]

    confirm_response = client.get(f"/api/v1/leads/confirm?token={token}")

    assert confirm_response.status_code == 200
    confirm_body = confirm_response.json()
    assert confirm_body["ok"] is True
    assert confirm_body["lead"]["status"] == "confirmed"


def test_list_waitlist_leads(client: TestClient) -> None:
    token = _register(client, "dario.list@example.com")

    client.post(
        "/api/v1/leads",
        json={
            "name": "Dario Test",
            "email": "dario.list@example.com",
            "device": "both",
            "source": "landing-page",
        },
    )

    response = client.get(
        "/api/v1/leads?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) >= 1
    assert body["items"][0]["lead_id"]
    assert "next_cursor" in body
    assert "has_more" in body


def test_resend_confirmation_rotates_token(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/leads",
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
        "/api/v1/leads/resend-confirmation",
        json={"email": "resend@example.com"},
    )
    assert resend_response.status_code == 200
    resend_body = resend_response.json()
    second_preview = resend_body["confirmation_url_preview"]
    second_token = parse_qs(urlparse(second_preview).query)["token"][0]

    assert first_token != second_token
    assert resend_body["lead"]["status"] == "pending"

    stale_confirmation = client.get(f"/api/v1/leads/confirm?token={first_token}")
    assert stale_confirmation.status_code == 400

    fresh_confirmation = client.get(f"/api/v1/leads/confirm?token={second_token}")
    assert fresh_confirmation.status_code == 200


def test_resend_confirmation_nonexistent_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/leads/resend-confirmation",
        json={"email": "notfound@example.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lead"] is None
    assert "Si este correo existe" in body["message"]
