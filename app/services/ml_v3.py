from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

import joblib
import librosa
import numpy as np
from fastapi import UploadFile

from app.core.config import settings
from app.utils.audio import convert_to_wav

logger = logging.getLogger(__name__)

SR = 16000
SEGMENT_SEC = 30
N_MFCC = 20


class _ModoInfo(TypedDict):
    umbral_alerta: float
    umbral_critico: float
    descripcion: str


MODOS: dict[str, _ModoInfo] = {
    "screening": {
        "umbral_alerta": 0.20,
        "umbral_critico": 0.55,
        "descripcion": "Usuarios nuevos sin diagnostico previo",
    },
    "seguimiento": {
        "umbral_alerta": 0.40,
        "umbral_critico": 0.65,
        "descripcion": "Pacientes diagnosticados monitoreo preciso",
    },
}


@dataclass(slots=True)
class DualModelArtifacts:
    model_spo2: Any
    model_audio: Any
    scaler_spo2: Any
    scaler_audio: Any
    metadata: dict
    weight_spo2: float
    weight_audio: float


_artifacts_cache: DualModelArtifacts | None = None
_cache_lock = Lock()


def _model_dir() -> Path:
    return Path(settings.ml_v3_model_dir)


def _required_files(root: Path) -> dict[str, Path]:
    return {
        "model_spo2": root / "model_spo2_v3.joblib",
        "model_audio": root / "model_audio_v3.joblib",
        "scaler_spo2": root / "scaler_spo2_v3.joblib",
        "scaler_audio": root / "scaler_audio_v3.joblib",
        "metadata": root / "metadata_v3.json",
    }


def _load_artifacts() -> DualModelArtifacts:
    global _artifacts_cache

    if _artifacts_cache is not None:
        return _artifacts_cache

    with _cache_lock:
        if _artifacts_cache is not None:
            return _artifacts_cache

        root = _model_dir()
        files = _required_files(root)
        missing = [name for name, path in files.items() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f"Faltan artefactos ML v3 en {root}: {', '.join(missing)}"
            )

        try:
            model_spo2 = joblib.load(files["model_spo2"])
            model_audio = joblib.load(files["model_audio"])
            scaler_spo2 = joblib.load(files["scaler_spo2"])
            scaler_audio = joblib.load(files["scaler_audio"])
        except Exception as exc:
            logger.error("Artefactos ML v3 corruptos o incompatibles: %s", exc)
            raise FileNotFoundError(
                f"Artefactos ML v3 no cargables en {root}. Revisa la instalación."
            ) from exc

        with files["metadata"].open(encoding="utf-8") as handle:
            metadata = json.load(handle)

        _artifacts_cache = DualModelArtifacts(
            model_spo2=model_spo2,
            model_audio=model_audio,
            scaler_spo2=scaler_spo2,
            scaler_audio=scaler_audio,
            metadata=metadata,
            weight_spo2=float(metadata["rendimiento"]["peso_spo2"]),
            weight_audio=float(metadata["rendimiento"]["peso_audio"]),
        )

        return _artifacts_cache


def extraer_features_audio(y: np.ndarray) -> np.ndarray:
    mfccs = np.mean(librosa.feature.mfcc(y=y, sr=SR, n_mfcc=N_MFCC), axis=1)
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
    rms = float(np.mean(librosa.feature.rms(y=y)))
    return np.concatenate([mfccs, [zcr, rms]])


def calcular_spo2_drop(spo2_values: list[float]) -> float:
    arr = np.array(spo2_values)
    arr = arr[(arr > 50) & (arr <= 100)]
    if len(arr) < 2:
        return 0.0
    return float(np.percentile(arr, 95) - np.min(arr))


def clasificar_nivel(prob: float, modo: str) -> str:
    m = MODOS[modo]
    if prob >= m["umbral_critico"]:
        return "CRITICO"
    if prob >= m["umbral_alerta"]:
        return "ALERTA"
    return "NORMAL"


def pad_audio(y: np.ndarray, target_len: int) -> np.ndarray:
    if len(y) >= target_len:
        return y[:target_len]

    reps = int(np.ceil(target_len / len(y)))
    tiled = np.tile(y, reps)[:target_len]
    fade = min(SR * 2, target_len // 4)
    tiled[-fade:] *= np.linspace(1.0, 0.1, fade)
    return tiled


def describe_modes() -> dict:
    return {
        modo: {
            **info,
            "umbrales": {
                "alerta": info["umbral_alerta"],
                "critico": info["umbral_critico"],
            },
        }
        for modo, info in MODOS.items()
    }


def health_payload() -> dict:
    try:
        artifacts = _load_artifacts()
    except FileNotFoundError:
        return {
            "status": "model_missing",
            "version": None,
            "modelo": None,
            "modos_disponibles": list(MODOS.keys()),
        }

    rendimiento = artifacts.metadata.get("rendimiento", {})
    return {
        "status": "ok",
        "version": artifacts.metadata.get("version"),
        "modelo": {
            "auc_ensemble": rendimiento.get("auc_ensemble"),
            "auc_spo2": rendimiento.get("auc_spo2"),
            "auc_audio": rendimiento.get("auc_audio"),
        },
        "modos_disponibles": list(MODOS.keys()),
    }


async def predict_dual_mode(
    audio: UploadFile,
    spo2: str,
    modo: str,
    perfil: str,
) -> dict:
    if modo not in MODOS:
        raise ValueError("Modo invalido. Usar: screening | seguimiento")

    try:
        spo2_list = [float(x.strip()) for x in spo2.split(",")]
        spo2_drop = calcular_spo2_drop(spo2_list)
    except ValueError as exc:
        raise ValueError("Formato SpO2 invalido. Ejemplo: 95,94,93,91") from exc

    _ALLOWED_MIME = {"audio/wav", "audio/wave", "audio/x-wav", "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "audio/mpeg", "audio/x-mpeg"}
    if audio.content_type and audio.content_type not in _ALLOWED_MIME:
        raise ValueError(f"Tipo de archivo no soportado: {audio.content_type}")

    # Validar y leer el audio ANTES de cargar modelos: evita DoS por archivos
    # gigantes y no toca disco/modelos si el archivo es inválido.
    _SAFE_SUFFIXES = {".wav", ".m4a", ".aac", ".mp4", ".caf", ".mp3"}
    raw_suffix = os.path.splitext(audio.filename or "audio.wav")[1].lower() or ".wav"
    suffix = raw_suffix if raw_suffix in _SAFE_SUFFIXES else ".wav"
    converted_audio_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            payload = await audio.read(settings.max_v3_audio_size_bytes + 1)
            if not payload:
                raise ValueError("Audio vacío.")
            if len(payload) > settings.max_v3_audio_size_bytes:
                raise ValueError("Audio demasiado grande para procesamiento.")
            tmp_file.write(payload)
            audio_path = tmp_file.name

        artifacts = _load_artifacts()

        # Convertir a WAV si es necesario (librosa tiene problemas con m4a)
        if not audio_path.lower().endswith('.wav'):
            converted_audio_path = convert_to_wav(audio_path)
            audio_path = converted_audio_path

        y, _ = librosa.load(audio_path, sr=SR, mono=True)

        if len(y) < SR * 2:
            raise ValueError("Audio demasiado corto minimo 2 segundos")

        y = pad_audio(y, SR * SEGMENT_SEC)

        max_amp = np.max(np.abs(y))
        if max_amp > 0:
            y = y / max_amp

        audio_feat = extraer_features_audio(y).reshape(1, -1)
        audio_feat_s = artifacts.scaler_audio.transform(audio_feat)
        prob_audio = float(artifacts.model_audio.predict_proba(audio_feat_s)[0][1])

        spo2_feat = artifacts.scaler_spo2.transform(np.array([[spo2_drop]]))
        prob_spo2 = float(artifacts.model_spo2.predict_proba(spo2_feat)[0][1])

        prob_final = artifacts.weight_spo2 * prob_spo2 + artifacts.weight_audio * prob_audio
        nivel = clasificar_nivel(prob_final, modo)

        interpretacion = {
            "NORMAL": "Sin eventos detectados en este segmento.",
            "ALERTA": "Posible evento respiratorio. Revisar segmentos consecutivos.",
            "CRITICO": "Evento severo detectado. Se recomienda consulta medica.",
        }[nivel]

        return {
            "nivel": nivel,
            "interpretacion": interpretacion,
            "probabilidad": round(prob_final, 4),
            "detalle": {
                "prob_audio": round(prob_audio, 4),
                "prob_spo2": round(prob_spo2, 4),
                "spo2_drop_pts": round(spo2_drop, 2),
                "peso_audio": artifacts.weight_audio,
                "peso_spo2": artifacts.weight_spo2,
            },
            "modo": modo,
            "perfil": perfil,
            "version": str(artifacts.metadata.get("version", "v3")),
        }
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_file.name)

        # Limpiar archivo convertido si se creó
        if converted_audio_path:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(converted_audio_path)
