"""
A.S.A.P. — Sleep Apnea Detection API
Versión: v3_universal_dual_mode
Fecha:   2026-03-08

Modelo ensemble dual:
  - model_spo2_v3.joblib   → GradientBoosting sobre SpO2 drop
  - model_audio_v3.joblib  → RandomForest sobre MFCCs + ZCR + RMS
  - AUC ensemble: 0.8373

Modos:
  - screening   → umbral 0.20, Sens 70%, Spec 80%  (usuarios nuevos)
  - seguimiento → umbral 0.40, Sens 52%, Spec 93%  (pacientes diagnosticados)

Uso:
  uvicorn main_v3:app --reload --port 8000

Endpoints:
  POST /predict?modo=screening&spo2=95,94,93,91&perfil=general
  GET  /health
  GET  /modos
"""

import os
import json
import tempfile

import joblib
import librosa
import numpy as np
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# ── Configuración ─────────────────────────────────────────────────────────────
MODEL_DIR   = os.path.join(os.path.dirname(__file__), "models")
SR          = 16000
SEGMENT_SEC = 30
N_MFCC      = 20

# ── Cargar modelos al iniciar ─────────────────────────────────────────────────
model_spo2  = joblib.load(os.path.join(MODEL_DIR, "model_spo2_v3.joblib"))
model_audio = joblib.load(os.path.join(MODEL_DIR, "model_audio_v3.joblib"))
sc_spo2     = joblib.load(os.path.join(MODEL_DIR, "scaler_spo2_v3.joblib"))
sc_audio    = joblib.load(os.path.join(MODEL_DIR, "scaler_audio_v3.joblib"))

with open(os.path.join(MODEL_DIR, "metadata_v3.json"), encoding="utf-8") as f:
    META = json.load(f)

W_SPO2  = META["rendimiento"]["peso_spo2"]    # 0.80
W_AUDIO = META["rendimiento"]["peso_audio"]   # 0.20

# ── Umbrales por modo ─────────────────────────────────────────────────────────
MODOS = {
    "screening": {
        "umbral_alerta":  0.20,   # Sens 70% — captura la mayoría de eventos
        "umbral_critico": 0.55,   # Spec 97% — evento severo
        "descripcion":    "Usuarios nuevos sin diagnóstico previo",
    },
    "seguimiento": {
        "umbral_alerta":  0.40,   # Spec 93% — alta precisión
        "umbral_critico": 0.65,   # Spec 99% — acción inmediata
        "descripcion":    "Pacientes diagnosticados — monitoreo preciso",
    },
}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "A.S.A.P. Sleep Apnea API",
    description = "Detección de apnea del sueño por audio + SpO2",
    version     = META["version"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Funciones ─────────────────────────────────────────────────────────────────
def extraer_features_audio(y: np.ndarray) -> np.ndarray:
    """Extrae 22 features de audio: 20 MFCCs + ZCR + RMS."""
    mfccs = np.mean(librosa.feature.mfcc(y=y, sr=SR, n_mfcc=N_MFCC), axis=1)
    zcr   = float(np.mean(librosa.feature.zero_crossing_rate(y)))
    rms   = float(np.mean(librosa.feature.rms(y=y)))
    return np.concatenate([mfccs, [zcr, rms]])


def calcular_spo2_drop(spo2_values: list[float]) -> float:
    """Calcula la caída de SpO2 en la ventana (percentil 95 - mínimo)."""
    arr = np.array(spo2_values)
    arr = arr[(arr > 50) & (arr <= 100)]   # filtrar artefactos
    if len(arr) < 2:
        return 0.0
    return float(np.percentile(arr, 95) - np.min(arr))


def clasificar_nivel(prob: float, modo: str) -> str:
    """Clasifica en NORMAL / ALERTA / CRITICO según modo clínico."""
    m = MODOS[modo]
    if prob >= m["umbral_critico"]:
        return "CRITICO"
    if prob >= m["umbral_alerta"]:
        return "ALERTA"
    return "NORMAL"


def pad_audio(y: np.ndarray, target_len: int) -> np.ndarray:
    """Padding con repetición + fade out para llegar a 30s."""
    if len(y) >= target_len:
        return y[:target_len]
    reps   = int(np.ceil(target_len / len(y)))
    tiled  = np.tile(y, reps)[:target_len]
    fade   = min(SR * 2, target_len // 4)
    tiled[-fade:] *= np.linspace(1.0, 0.1, fade)
    return tiled


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/predict")
async def predict(
    audio: UploadFile = File(..., description="Audio WAV de 30s grabado pasivamente"),
    spo2:  str        = Query(
        default     = "95,95,94,94,95",
        description = "Valores SpO2 separados por coma durante el segmento"
    ),
    modo:  str        = Query(
        default     = "screening",
        description = "Modo clínico: 'screening' o 'seguimiento'"
    ),
    perfil: str       = Query(
        default     = "general",
        description = "Perfil del paciente: 'general' o 'matias'"
    ),
):
    """
    Predice apnea del sueño a partir de un segmento de audio de 30s + SpO2.

    Retorna nivel NORMAL / ALERTA / CRITICO con probabilidades detalladas.
    """
    # Validar modo
    if modo not in MODOS:
        return {"error": "Modo inválido. Usar: screening | seguimiento"}

    # Parsear SpO2
    try:
        spo2_list = [float(x.strip()) for x in spo2.split(",")]
        spo2_drop = calcular_spo2_drop(spo2_list)
    except ValueError:
        return {"error": "Formato SpO2 inválido. Ejemplo: 95,94,93,91"}

    # Guardar audio temporalmente
    suffix   = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
    tmp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp_file.write(await audio.read())
        tmp_file.close()

        # Cargar y procesar audio
        y, _ = librosa.load(tmp_file.name, sr=SR, mono=True)

        if len(y) < SR * 2:
            return {"error": "Audio demasiado corto — mínimo 2 segundos"}

        # Padding a exactamente 30s
        y = pad_audio(y, SR * SEGMENT_SEC)

        # Normalizar amplitud
        max_amp = np.max(np.abs(y))
        if max_amp > 0:
            y = y / max_amp

        # ── Inferencia modelo audio ───────────────────────────────────────
        audio_feat   = extraer_features_audio(y).reshape(1, -1)
        audio_feat_s = sc_audio.transform(audio_feat)
        prob_audio   = float(model_audio.predict_proba(audio_feat_s)[0][1])

        # ── Inferencia modelo SpO2 ────────────────────────────────────────
        spo2_feat    = sc_spo2.transform(np.array([[spo2_drop]]))
        prob_spo2    = float(model_spo2.predict_proba(spo2_feat)[0][1])

        # ── Ensemble ──────────────────────────────────────────────────────
        prob_final   = W_SPO2 * prob_spo2 + W_AUDIO * prob_audio
        nivel        = clasificar_nivel(prob_final, modo)

        # ── Interpretación clínica ────────────────────────────────────────
        interpretacion = {
            "NORMAL":  "Sin eventos detectados en este segmento.",
            "ALERTA":  "Posible evento respiratorio. Revisar segmentos consecutivos.",
            "CRITICO": "Evento severo detectado. Se recomienda consulta médica.",
        }[nivel]

        return {
            "nivel":           nivel,
            "interpretacion":  interpretacion,
            "probabilidad":    round(prob_final, 4),
            "detalle": {
                "prob_audio":      round(prob_audio, 4),
                "prob_spo2":       round(prob_spo2,  4),
                "spo2_drop_pts":   round(spo2_drop,  2),
                "peso_audio":      W_AUDIO,
                "peso_spo2":       W_SPO2,
            },
            "modo":    modo,
            "perfil":  perfil,
            "version": META["version"],
        }

    finally:
        os.unlink(tmp_file.name)


@app.get("/health")
def health():
    """Estado del servicio y métricas del modelo."""
    return {
        "status":  "ok",
        "version": META["version"],
        "modelo": {
            "auc_ensemble": META["rendimiento"]["auc_ensemble"],
            "auc_spo2":     META["rendimiento"]["auc_spo2"],
            "auc_audio":    META["rendimiento"]["auc_audio"],
        },
        "modos_disponibles": list(MODOS.keys()),
    }


@app.get("/modos")
def modos():
    """Descripción de los modos clínicos disponibles."""
    return {
        modo: {
            **info,
            "umbrales": {
                "alerta":  info["umbral_alerta"],
                "critico": info["umbral_critico"],
            }
        }
        for modo, info in MODOS.items()
    }


@app.get("/")
def root():
    return {
        "app":     "A.S.A.P. Sleep Apnea Detection",
        "version": META["version"],
        "docs":    "/docs",
        "health":  "/health",
    }
