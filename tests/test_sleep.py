from array import array
import math
import io
import wave
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.db.base import Base
from app.db.models import SleepDetectionLog
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
    app.state.test_engine = engine
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.state.test_engine = None
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


def test_subir_fragmento_audio(client: TestClient) -> None:
    token = _register(client, "sleep.fragment@example.com")

    start = client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 34},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    response = client.post(
        f"/api/sleep/sesiones/{session_id}/fragmento",
        headers={"Authorization": f"Bearer {token}"},
        files={"fragmento": ("fragmento_0001.m4a", b"FAKEAUDIO" * 1024, "audio/mp4")},
        data={"fragment_index": "1", "duration_seconds": "30"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["fragmento"]["session_id"] == session_id
    assert body["fragmento"]["fragment_index"] == 1
    assert body["fragmento"]["bytes_size"] > 0


def _build_wav_fragment(duration_seconds: int = 30, sample_rate: int = 16000) -> bytes:
    total_samples = duration_seconds * sample_rate
    tone_frequency_hz = 130.0

    samples = array("h")
    for sample_index in range(total_samples):
        loud_phase = (sample_index // (sample_rate // 2)) % 2 == 0
        amplitude = 14000 if loud_phase else 900
        value = int(amplitude * math.sin(2 * math.pi * tone_frequency_hz * (sample_index / sample_rate)))
        samples.append(value)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.tobytes())

    return buffer.getvalue()


def test_finalizar_sesion_con_fragmentos_y_logs_confianza(client: TestClient) -> None:
    token = _register(client, "sleep.analysis@example.com")

    start = client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 37},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    fragment_bytes = _build_wav_fragment()
    upload = client.post(
        f"/api/sleep/sesiones/{session_id}/fragmento",
        headers={"Authorization": f"Bearer {token}"},
        files={"fragmento": ("fragment_0001.wav", fragment_bytes, "audio/wav")},
        data={"fragment_index": "1", "duration_seconds": "30"},
    )
    assert upload.status_code == 201

    finish = client.post(
        f"/api/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"avg_oxygen": 95},
    )

    assert finish.status_code == 200
    finish_body = finish.json()
    assert finish_body["sesion"]["sleep_score"] is not None
    assert finish_body["sesion"]["snore_count"] >= 0
    assert finish_body["sesion"]["apnea_events"] >= 0

    test_engine = client.app.state.test_engine
    assert test_engine is not None
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    with testing_session() as db:
        logs = db.scalars(select(SleepDetectionLog).where(SleepDetectionLog.session_id == session_id)).all()

    assert len(logs) >= 1
    assert all(log.confidence_score >= 0 for log in logs)


def test_listar_detecciones_por_sesion(client: TestClient) -> None:
    token = _register(client, "sleep.logs.endpoint@example.com")

    start = client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 33},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    fragment_bytes = _build_wav_fragment()
    upload = client.post(
        f"/api/sleep/sesiones/{session_id}/fragmento",
        headers={"Authorization": f"Bearer {token}"},
        files={"fragmento": ("fragment_0001.wav", fragment_bytes, "audio/wav")},
        data={"fragment_index": "0", "duration_seconds": "30"},
    )
    assert upload.status_code == 201

    finish = client.post(
        f"/api/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"avg_oxygen": 95},
    )
    assert finish.status_code == 200

    response = client.get(
        f"/api/sleep/sesiones/{session_id}/detecciones?limit=200",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    first = body[0]
    assert first["session_id"] == session_id
    assert first["label"] in {"Normal", "Ronquido", "Apnea"}
    assert 0 <= first["confidence_score"] <= 1


def test_guardar_feedback_sesion_finalizada(client: TestClient) -> None:
    token = _register(client, "sleep.feedback@example.com")

    start = client.post(
        "/api/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 30},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 2, "apnea_events": 1, "avg_oxygen": 96},
    )
    assert finish.status_code == 200

    response = client.post(
        f"/api/sleep/sesiones/{session_id}/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "calificacion_descanso": 4,
            "desperto_cansado": False,
            "comentario": "Me senti mejor que ayer.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["feedback"]["session_id"] == session_id
    assert body["feedback"]["calificacion_descanso"] == 4
