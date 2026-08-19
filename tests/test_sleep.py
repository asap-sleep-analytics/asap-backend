import io
import math
import wave
from array import array
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import SleepDetectionLog
from app.services.sleep import _analysis_label, _compute_sleep_score


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Sleep Tester",
            "email": email,
            "password": "ClaveSegura123",
            "acepta_terminos_condiciones": True,
            "acepta_consentimiento_datos": True,
            "acepta_disclaimer_medico": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_calibracion_ruido_alto(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sleep/calibracion",
        json={"ambient_noise_level": 62},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["nivel_ruido"] == "alto"


def test_iniciar_y_finalizar_sesion(client: TestClient) -> None:
    token = _register(client, "sleep.session@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 36},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
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
    # Sin fragmentos de audio no hay inferencia: timeline vacío y fuente explícita.
    assert body["sesion"]["continuidad"] == []
    assert body["sesion"]["model_source"] is None


def test_listar_sesiones(client: TestClient) -> None:
    token = _register(client, "sleep.list@example.com")

    client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 32},
    )

    response = client.get(
        "/api/v1/sleep/sesiones?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) >= 1
    assert "next_cursor" in body
    assert "has_more" in body


def test_subir_fragmento_audio(client: TestClient) -> None:
    token = _register(client, "sleep.fragment@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 34},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    response = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/fragmento",
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
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 37},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    fragment_bytes = _build_wav_fragment()
    upload = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/fragmento",
        headers={"Authorization": f"Bearer {token}"},
        files={"fragmento": ("fragment_0001.wav", fragment_bytes, "audio/wav")},
        data={"fragment_index": "1", "duration_seconds": "30"},
    )
    assert upload.status_code == 201

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
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
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 33},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    fragment_bytes = _build_wav_fragment()
    upload = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/fragmento",
        headers={"Authorization": f"Bearer {token}"},
        files={"fragmento": ("fragment_0001.wav", fragment_bytes, "audio/wav")},
        data={"fragment_index": "0", "duration_seconds": "30"},
    )
    assert upload.status_code == 201

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"avg_oxygen": 95},
    )
    assert finish.status_code == 200

    response = client.get(
        f"/api/v1/sleep/sesiones/{session_id}/detecciones?limit=200",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "next_cursor" in body
    assert len(body["items"]) >= 1
    first = body["items"][0]
    assert first["session_id"] == session_id
    assert first["label"] in {"Normal", "Ronquido", "Apnea"}
    assert 0 <= first["confidence_score"] <= 1


def test_guardar_feedback_sesion_finalizada(client: TestClient) -> None:
    token = _register(client, "sleep.feedback@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 30},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 2, "apnea_events": 1, "avg_oxygen": 96},
    )
    assert finish.status_code == 200

    response = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/feedback",
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


def test_calcular_puntaje_límites() -> None:
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

    # Duración nula o negativa → 0
    assert _compute_sleep_score(base, base, snore_count=0, apnea_events=0) == 0

    # Puntaje está acotado en [0, 100]
    assert _compute_sleep_score(base, base.replace(hour=10), snore_count=0, apnea_events=0) == 100
    assert _compute_sleep_score(base, base.replace(hour=2), snore_count=9999, apnea_events=99) == 0

    # Una noche limpia de 2 h da 25 puntos exactos, sin penalización
    assert _compute_sleep_score(base, base.replace(hour=2), snore_count=0, apnea_events=0) == 25

    # Las apneas penalizan más que los ronquidos
    duration_penalized_apnea = _compute_sleep_score(base, base.replace(hour=2), snore_count=0, apnea_events=2)
    duration_penalized_snore = _compute_sleep_score(base, base.replace(hour=2), snore_count=10, apnea_events=0)
    assert duration_penalized_snore > duration_penalized_apnea

    # El resultado coincide con la fórmula cerrada
    score = _compute_sleep_score(base, base.replace(hour=2), snore_count=20, apnea_events=3)
    snore_freq = 20 / 2
    expected = int(max(0, min(100, round(2 * 12.5 - 3 * 8.0 - snore_freq * 0.75))))
    assert score == expected


def test_analisis_etiqueta_fuente() -> None:
    assert _analysis_label(None, None) is None
    assert _analysis_label("sklearn", "sklearn-1.9.0") == "Análisis con modelo de sueño entrenado"
    assert _analysis_label("heuristic", "heuristic-amplitude-v1") == "Análisis estimado con heurística de audio"
    assert _analysis_label("custom", "custom-v2") == "Análisis con custom"


def test_finalizar_sesion_expone_fuente_sin_audio(client: TestClient) -> None:
    token = _register(client, "sleep.fuente@example.com")

    start = client.post(
        "/api/v1/sleep/sesiones/iniciar",
        headers={"Authorization": f"Bearer {token}"},
        json={"ambient_noise_level": 33},
    )
    assert start.status_code == 201
    session_id = start.json()["sesion"]["session_id"]

    finish = client.post(
        f"/api/v1/sleep/sesiones/{session_id}/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 4, "apnea_events": 1, "avg_oxygen": 97},
    )

    assert finish.status_code == 200
    body = finish.json()["sesion"]
    assert body["model_source"] is None
    assert body["model_version"] is None
    assert body["analysis_label"] is None


def test_finalizar_sesion_inexistente_404(client: TestClient) -> None:
    token = _register(client, "sleep.noexiste@example.com")

    response = client.post(
        "/api/v1/sleep/sesiones/no-existe/finalizar",
        headers={"Authorization": f"Bearer {token}"},
        json={"snore_count": 0, "apnea_events": 0},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert "no encontrada" in body["detail"].lower()
