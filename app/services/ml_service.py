from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn import __version__ as sklearn_version

from app.core.config import settings
from app.services.audio_processor import SessionAudioBatch

LABEL_NORMAL = "Normal"
LABEL_SNORE = "Ronquido"
LABEL_APNEA = "Apnea"


@dataclass(slots=True)
class WindowDetection:
    window_index: int
    start_second: float
    end_second: float
    label: str
    confidence: float


@dataclass(slots=True)
class SleepInferenceResult:
    detections: list[WindowDetection]
    source: str
    model_version: str


def _normalize_label(value: object) -> str:
    raw = str(value).strip().lower()

    if raw in {"0", "normal", "norm"}:
        return LABEL_NORMAL
    if raw in {"1", "ronquido", "snore", "snoring"} or "ronq" in raw or "snor" in raw:
        return LABEL_SNORE
    if raw in {"2", "apnea"} or "apnea" in raw:
        return LABEL_APNEA

    return LABEL_NORMAL


def _clamp_confidence(value: float) -> float:
    return float(max(0.05, min(0.99, value)))


class SleepModel:
    def __init__(self, model_path: str | Path | None = None):
        self._model_path = Path(model_path or settings.ml_sleep_model_path)
        self._model = None
        self._loaded = False

    def _ensure_model(self) -> None:
        if self._loaded:
            return

        self._loaded = True
        if not self._model_path.exists():
            self._model = None
            return

        try:
            self._model = joblib.load(self._model_path)
        except Exception:
            self._model = None

    @property
    def is_trained(self) -> bool:
        self._ensure_model()
        return self._model is not None

    def classify_batch(self, batch: SessionAudioBatch) -> SleepInferenceResult:
        if not batch.windows:
            return SleepInferenceResult(detections=[], source="heuristic", model_version="heuristic-amplitude-v1")

        self._ensure_model()
        if self._model is not None:
            try:
                return self._predict_with_model(batch)
            except Exception:
                pass

        return self._predict_with_heuristic(batch)

    def _predict_with_model(self, batch: SessionAudioBatch) -> SleepInferenceResult:
        matrix = np.vstack([window.feature_vector for window in batch.windows]).astype(np.float32)
        expected = getattr(self._model, "n_features_in_", None)

        if isinstance(expected, int) and expected > 0 and matrix.shape[1] != expected:
            if matrix.shape[1] > expected:
                matrix = matrix[:, :expected]
            else:
                padding = np.zeros((matrix.shape[0], expected - matrix.shape[1]), dtype=np.float32)
                matrix = np.hstack([matrix, padding])

        predictions = self._model.predict(matrix)
        probabilities = self._model.predict_proba(matrix) if hasattr(self._model, "predict_proba") else None

        detections: list[WindowDetection] = []
        for index, window in enumerate(batch.windows):
            label = _normalize_label(predictions[index])

            if probabilities is not None and len(probabilities[index]) > 0:
                confidence = float(np.max(probabilities[index]))
            else:
                confidence = 0.55

            detections.append(
                WindowDetection(
                    window_index=window.window_index,
                    start_second=window.start_second,
                    end_second=window.end_second,
                    label=label,
                    confidence=_clamp_confidence(confidence),
                )
            )

        return SleepInferenceResult(
            detections=detections,
            source="sklearn",
            model_version=f"sklearn-{sklearn_version}",
        )

    def _predict_with_heuristic(self, batch: SessionAudioBatch) -> SleepInferenceResult:
        db_values = np.array([window.rms_db for window in batch.windows], dtype=np.float32)

        high_threshold = float(max(np.percentile(db_values, 80), -24.0))
        low_threshold = float(min(np.percentile(db_values, 20), -39.0))

        apnea_indexes: set[int] = set()
        streak: list[int] = []

        for index, db_value in enumerate(db_values):
            if db_value <= low_threshold:
                streak.append(index)
                continue

            if len(streak) >= 2:
                apnea_indexes.update(streak)
            streak = []

        if len(streak) >= 2:
            apnea_indexes.update(streak)

        detections: list[WindowDetection] = []
        for index, window in enumerate(batch.windows):
            db_value = float(db_values[index])

            if index in apnea_indexes:
                label = LABEL_APNEA
                confidence = 0.58 + min(0.35, max(0.0, (low_threshold - db_value) / 24))
            elif db_value >= high_threshold:
                label = LABEL_SNORE
                confidence = 0.55 + min(0.35, max(0.0, (db_value - high_threshold) / 18))
            else:
                label = LABEL_NORMAL
                confidence = 0.5 + min(0.18, max(0.0, (high_threshold - db_value) / 40))

            detections.append(
                WindowDetection(
                    window_index=window.window_index,
                    start_second=window.start_second,
                    end_second=window.end_second,
                    label=label,
                    confidence=_clamp_confidence(float(confidence)),
                )
            )

        return SleepInferenceResult(
            detections=detections,
            source="heuristic",
            model_version="heuristic-amplitude-v1",
        )
