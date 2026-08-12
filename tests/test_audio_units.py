from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.services.audio_processor import (
    _is_audio_fragment,
    _preprocess_signal,
    _window_generator,
    build_session_audio_batch,
    cleanup_session_fragments,
)


class TestIsAudioFragment:
    @pytest.mark.parametrize("suffix", [".wav", ".m4a", ".aac", ".mp4", ".flac", ".ogg", ".caf"])
    def test_extensiones_soportadas(self, suffix: str) -> None:
        assert _is_audio_fragment(Path(f"audio{suffix}"))

    def test_extension_no_soportada(self) -> None:
        assert not _is_audio_fragment(Path("audio.txt"))
        assert not _is_audio_fragment(Path("audio.mp3"))
        assert not _is_audio_fragment(Path("audio"))
        assert not _is_audio_fragment(Path("audio.md"))

    def test_case_insensitive(self) -> None:
        assert _is_audio_fragment(Path("audio.WAV"))
        assert _is_audio_fragment(Path("audio.M4A"))


class TestWindowGenerator:
    def test_ventanas_no_solapadas_con_hop_completo(self) -> None:
        signal = np.zeros(16000 * 3, dtype=np.float32)
        windows = list(_window_generator(signal, sample_rate=16000, window_seconds=1.0))
        assert len(windows) == 3
        assert [start for _, start, _ in windows] == [0.0, 1.0, 2.0]

    def test_ventana_final_muy_corta_se_descarta(self) -> None:
        signal = np.zeros(16000 * 2 + 500, dtype=np.float32)
        windows = list(_window_generator(signal, sample_rate=16000, window_seconds=1.0))
        assert len(windows) == 2

    def test_senal_vacia_sin_ventanas(self) -> None:
        windows = list(_window_generator(np.zeros(0), sample_rate=16000, window_seconds=1.0))
        assert windows == []


class TestPreprocessSignal:
    def test_normaliza_y_devuelve_float32(self) -> None:
        signal = np.random.randn(16000).astype(np.float64)
        result = _preprocess_signal(signal, sample_rate=16000)
        assert result.dtype == np.float32
        assert np.max(np.abs(result)) <= 1.0

    def test_senal_vacia_no_falla(self) -> None:
        result = _preprocess_signal(np.zeros(0, dtype=np.float32), sample_rate=16000)
        assert result.size == 0


class TestBuildSessionAudioBatch:
    def test_sin_directorio_devuelve_batch_vacio(self, tmp_path: Path) -> None:
        batch = build_session_audio_batch("no-existe", tmp_path)
        assert batch.windows == []
        assert batch.duration_seconds == 0.0
        assert batch.mean_rms_db is None

    def test_ignora_archivos_no_audio(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "sesion-1"
        session_dir.mkdir()
        (session_dir / "nota.txt").write_text("hola", encoding="utf-8")

        batch = build_session_audio_batch("sesion-1", tmp_path)
        assert batch.fragment_paths == []

    def test_cleanup_elimina_directorio(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "sesion-2"
        session_dir.mkdir()
        (session_dir / "f.wav").write_bytes(b"data")

        cleanup_session_fragments("sesion-2", tmp_path)
        assert not session_dir.exists()

    def test_cleanup_no_falla_si_no_existe(self, tmp_path: Path) -> None:
        cleanup_session_fragments("nada", tmp_path)


class TestAudioUtils:
    def test_convert_to_wav_llama_ffmpeg_y_anade_sufijo(self, tmp_path: Path) -> None:
        from app.utils.audio import convert_to_wav

        source = tmp_path / "mi_audio.m4a"
        source.write_bytes(b"fakedata")

        expected = str(tmp_path / "mi_audio_converted.wav")
        with patch("app.utils.audio.subprocess.run") as mock_run:
            result = convert_to_wav(str(source))

        assert result == expected
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        assert "ffmpeg" in args
        assert str(source) in args
        assert expected == args[-1]
        assert "-ar" in args and "16000" in args
        assert "-ac" in args and "1" in args
