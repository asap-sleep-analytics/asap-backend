import numpy as np
import pytest

from app.services.audio_processor import SessionAudioBatch, SessionAudioWindow
from app.services.ml_service import (
    LABEL_APNEA,
    LABEL_NORMAL,
    LABEL_SNORE,
    SleepModel,
    _clamp_confidence,
    _normalize_label,
)


def _batch(rms_values: list[float]) -> SessionAudioBatch:
    windows = [
        SessionAudioWindow(
            window_index=index,
            start_second=float(index) * 5.0,
            end_second=float(index) * 5.0 + 5.0,
            rms_db=value,
            feature_vector=np.zeros(40, dtype=np.float32),
        )
        for index, value in enumerate(rms_values)
    ]
    return SessionAudioBatch(
        session_id="test-session",
        sample_rate=16000,
        mfcc_coefficients=20,
        fragment_paths=[],
        windows=windows,
        duration_seconds=float(len(windows) * 5),
        mean_rms_db=float(np.mean(rms_values)) if rms_values else None,
    )


class TestNormalizeLabel:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0", LABEL_NORMAL),
            ("1", LABEL_SNORE),
            ("2", LABEL_APNEA),
            ("normal", LABEL_NORMAL),
            ("Ronquido", LABEL_SNORE),
            ("Apnea", LABEL_APNEA),
            ("SNORING", LABEL_SNORE),
            ("RONQUIDO", LABEL_SNORE),
            ("apnea-2", LABEL_APNEA),
            ("cualquier-cosa", LABEL_NORMAL),
            ("", LABEL_NORMAL),
            (None, LABEL_NORMAL),
        ],
    )
    def test_mapeo_de_etiquetas(self, raw, expected) -> None:
        assert _normalize_label(raw) == expected


class TestClampConfidence:
    def test_clampa_por_arriba(self) -> None:
        assert _clamp_confidence(1.0) == 0.99

    def test_clampa_por_abajo(self) -> None:
        assert _clamp_confidence(0.0) == 0.05

    def test_valores_intermedios_se_mantienen(self) -> None:
        assert _clamp_confidence(0.5) == 0.5


class TestHeuristicPrediction:
    def test_batch_vacio_vuelve_heuristic_sin_detections(self) -> None:
        batch = _batch([])
        result = SleepModel(model_path="/no/existe/modelo.joblib").classify_batch(batch)

        assert result.source == "heuristic"
        assert result.detections == []

    def test_silencios_prolongados_se_marcan_como_apnea(self) -> None:
        batch = _batch(
            [-60.0, -59.0, -58.0, -57.0, -56.0, -55.0, -54.0, -5.0, -4.0, -3.0, -2.0, -1.0]
        )
        result = SleepModel(model_path="/no/existe/modelo.joblib").classify_batch(batch)

        labels = [d.label for d in result.detections]
        assert labels[0] == LABEL_APNEA
        assert labels[1] == LABEL_APNEA
        assert labels[2] == LABEL_APNEA
        assert result.source == "heuristic"

    def test_sonidos_fuertes_se_marcan_como_ronquido(self) -> None:
        batch = _batch([-10.0, -8.0, -9.0, -30.0, -28.0, -31.0])
        result = SleepModel(model_path="/no/existe/modelo.joblib").classify_batch(batch)

        labels = [d.label for d in result.detections]
        assert LABEL_SNORE in labels
        assert LABEL_NORMAL in labels

    def test_confidencias_estan_acotadas(self) -> None:
        batch = _batch([-70.0, -20.0, -10.0])
        result = SleepModel(model_path="/no/existe/modelo.joblib").classify_batch(batch)

        for detection in result.detections:
            assert 0.05 <= detection.confidence <= 0.99

    def test_indices_de_ventana_se_mantienen(self) -> None:
        batch = _batch([-60.0, -55.0, -50.0])
        result = SleepModel(model_path="/no/existe/modelo.joblib").classify_batch(batch)

        assert [d.window_index for d in result.detections] == [0, 1, 2]
