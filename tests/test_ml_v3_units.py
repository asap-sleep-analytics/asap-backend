import numpy as np
import pytest

from app.services.ml_v3 import (
    SR,
    calcular_spo2_drop,
    clasificar_nivel,
    describe_modes,
    extraer_features_audio,
    pad_audio,
)


class TestCalcularSpo2Drop:
    def test_drop_calculado_correctamente(self) -> None:
        valores = [95.0, 96.0, 94.0, 93.0, 92.0, 91.0, 95.0, 94.0]
        drop = calcular_spo2_drop(valores)
        assert drop > 0
        # percentil 95 de [91..96] menos el mínimo (91)
        assert drop == pytest.approx(float(np.percentile(valores, 95)) - 91.0, abs=0.01)

    def test_ignora_valores_fuera_de_rango(self) -> None:
        drop = calcular_spo2_drop([95.0, 10.0, 999.0, 94.0, -5.0])
        assert drop == pytest.approx(float(np.percentile([95.0, 94.0], 95)) - 94.0, abs=0.01)

    def test_menos_de_dos_valores_devuelve_cero(self) -> None:
        assert calcular_spo2_drop([95.0]) == 0.0
        assert calcular_spo2_drop([]) == 0.0


class TestClasificarNivel:
    def test_screening_normal(self) -> None:
        assert clasificar_nivel(0.10, "screening") == "NORMAL"

    def test_screening_alerta(self) -> None:
        assert clasificar_nivel(0.30, "screening") == "ALERTA"

    def test_screening_critico(self) -> None:
        assert clasificar_nivel(0.70, "screening") == "CRITICO"

    def test_seguimiento_umbrales_mas_exigentes(self) -> None:
        assert clasificar_nivel(0.30, "seguimiento") == "NORMAL"
        assert clasificar_nivel(0.50, "seguimiento") == "ALERTA"
        assert clasificar_nivel(0.70, "seguimiento") == "CRITICO"

    def test_limites_exactos(self) -> None:
        assert clasificar_nivel(0.20, "screening") == "ALERTA"
        assert clasificar_nivel(0.55, "screening") == "CRITICO"


class TestDescribeModos:
    def test_contiene_ambos_modos_con_umbrales(self) -> None:
        modos = describe_modes()
        assert set(modos.keys()) == {"screening", "seguimiento"}
        assert modos["screening"]["umbrales"]["alerta"] == 0.20
        assert modos["screening"]["umbrales"]["critico"] == 0.55
        assert modos["seguimiento"]["umbrales"]["critico"] == 0.65


class TestPadAudio:
    def test_pad_agrega_audio_silencioso(self) -> None:
        senal = np.ones(1000, dtype=np.float32)
        padded = pad_audio(senal, target_len=4000)
        assert len(padded) == 4000
        # Los primeros 1000 samples se mantienen
        assert np.all(padded[:1000] == 1.0)

    def test_pad_recorta_senal_mas_larga(self) -> None:
        senal = np.ones(10000, dtype=np.float32)
        padded = pad_audio(senal, target_len=2000)
        assert len(padded) == 2000

    def test_pad_longitud_exacta(self) -> None:
        senal = np.ones(3000, dtype=np.float32)
        padded = pad_audio(senal, target_len=3000)
        assert len(padded) == 3000

    def test_pad_no_introduce_clipping(self) -> None:
        senal = np.full(800, 1.0, dtype=np.float32)
        padded = pad_audio(senal, target_len=SR)
        assert len(padded) == SR
        assert np.max(padded) <= 1.0


class TestExtraerFeaturesAudio:
    def test_dimension_correcta(self) -> None:
        senal = np.random.randn(SR).astype(np.float32)
        features = extraer_features_audio(senal)
        # 20 MFCC + zcr + rms = 22
        assert features.shape == (22,)

    def test_senal_silenciosa_da_features_finitas(self) -> None:
        senal = np.zeros(SR, dtype=np.float32)
        features = extraer_features_audio(senal)
        assert features.shape == (22,)
        assert np.all(np.isfinite(features))
