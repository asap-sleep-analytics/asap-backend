from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.services.sleep import _compute_ahi, _estimate_desaturations


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "History Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _start_session(client: TestClient, token: str) -> str:
    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"start_time": datetime.now(UTC).isoformat()},
    )
    assert start.status_code == 201
    return start.json()["sesion"]["session_id"]


def test_ahi_en_sesion_finalizada(client: TestClient) -> None:
    token = _register(client, "ahi.finalizada@example.com")
    session_id = _start_session(client, token)

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "snore_count": 20,
            "apnea_events": 12,
            "avg_oxygen": 94,
            "desaturation_count": 5,
        },
    )
    assert finish.status_code == 200
    sesion = finish.json()["sesion"]

    start = datetime.fromisoformat(sesion["start_time"])
    end = datetime.fromisoformat(sesion["end_time"])
    duration_hours = max((end - start).total_seconds() / 3600, 0)

    assert sesion["apnea_events"] == 12
    assert sesion["ahi"] is not None
    assert abs(sesion["ahi"] - round(12 / duration_hours, 1)) < 0.01
    assert sesion["desaturation_count"] == 5


def test_ahi_nulo_sin_finalizar(client: TestClient) -> None:
    token = _register(client, "ahi.abierta@example.com")
    session_id = _start_session(client, token)

    # La sesión abierta se expone en el listado sin end_time.
    detail = client.get(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["sesion"]["end_time"] is None
    assert detail.json()["sesion"]["ahi"] is None


def test_desaturaciones_desde_curva_spo2(client: TestClient) -> None:
    token = _register(client, "spo2.curva@example.com")
    session_id = _start_session(client, token)

    # Curva: estable en 98-97, una caída a 93 (>=3pt) y recuperación.
    curva = [98, 98, 97, 97, 93, 93, 92, 97, 98, 98, 96, 94, 94, 98]

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "snore_count": 0,
            "apnea_events": 1,
            "spo2_samples": curva,
            "avg_oxygen": 96,
        },
    )
    assert finish.status_code == 200
    # La detección por curva sobreescribe el contador.
    assert finish.json()["sesion"]["desaturation_count"] >= 1


def test_detalle_sesion_404_si_no_es_del_usuario(client: TestClient) -> None:
    token_a = _register(client, "detalle.a@example.com")
    token_b = _register(client, "detalle.b@example.com")
    session_id = _start_session(client, token_a)

    forbidden = client.get(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden.status_code == 404

    own = client.get(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert own.status_code == 200


def test_borrar_sesion_individual(client: TestClient) -> None:
    token = _register(client, "delete.one@example.com")
    session_id = _start_session(client, token)

    client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 1, "apnea_events": 0},
    )

    response = client.delete(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    detail = client.get(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 404


def test_borrar_todas_las_sesiones(client: TestClient) -> None:
    token = _register(client, "delete.all@example.com")

    first = _start_session(client, token)
    second = _start_session(client, token)

    client.post(
        f"/api/v1/sleep/sesiones/{first}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 1, "apnea_events": 0},
    )
    client.post(
        f"/api/v1/sleep/sesiones/{second}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 2, "apnea_events": 1},
    )

    response = client.delete(
        "/api/v1/sleep/sesiones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    listing = client.get(
        "/api/v1/sleep/sesiones?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == 200
    assert listing.json()["items"] == []


def test_borrado_limpia_logs_y_feedback(client: TestClient) -> None:
    token = _register(client, "delete.cleanup@example.com")
    session_id = _start_session(client, token)

    client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 3, "apnea_events": 1},
    )
    client.post(
        f"/api/v1/sleep/sesiones/{session_id}/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={"calificacion_descanso": 4},
    )

    response = client.delete(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


def test_borrar_no_afecta_otro_usuario(client: TestClient) -> None:
    token_a = _register(client, "delete.owner@example.com")
    token_b = _register(client, "delete.other@example.com")
    session_id = _start_session(client, token_a)

    response = client.delete(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404

    still_owned = client.get(
        f"/api/v1/sleep/sesiones/{session_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert still_owned.status_code == 200


def test_compute_ahi_helpers() -> None:
    start = datetime(2026, 1, 1, 22, 0, tzinfo=UTC)
    end = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)

    assert _compute_ahi(20, start, end) == pytest.approx(2.5)
    assert _compute_ahi(0, start, end) == 0.0
    assert _compute_ahi(10, start, None) is None

    # Curva estable: sin desaturaciones.
    assert _estimate_desaturations([99, 99, 98, 98, 99]) == 0
    # Curva con una caída sostenida de 4 puntos.
    assert _estimate_desaturations([98, 98, 94, 94, 95, 98]) >= 1
    # Menos de 3 muestras no alcanza para decidir.
    assert _estimate_desaturations([98, 94]) == 0
    # Valores fuera de rango se ignoran.
    assert _estimate_desaturations([98, 0, 94, 94, 120, 98]) >= 1
