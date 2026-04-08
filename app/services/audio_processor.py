from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil

import librosa
import numpy as np

AUDIO_FRAGMENT_EXTENSIONS = {".m4a", ".wav", ".aac", ".mp4", ".caf", ".flac", ".ogg"}
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_MFCC_COEFFICIENTS = 20
DEFAULT_WINDOW_SECONDS = 5.0

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SessionAudioWindow:
    window_index: int
    start_second: float
    end_second: float
    rms_db: float
    feature_vector: np.ndarray


@dataclass(slots=True)
class SessionAudioBatch:
    session_id: str
    sample_rate: int
    mfcc_coefficients: int
    fragment_paths: list[Path]
    windows: list[SessionAudioWindow]
    duration_seconds: float
    mean_rms_db: float | None


def _is_audio_fragment(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_FRAGMENT_EXTENSIONS


def _load_fragment_signal(fragment_path: Path, sample_rate: int) -> np.ndarray | None:
    try:
        samples, _ = librosa.load(fragment_path.as_posix(), sr=sample_rate, mono=True)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("No se pudo procesar el fragmento de audio %s: %s", fragment_path, exc)
        return None

    if samples.size == 0:
        return None

    return np.asarray(samples, dtype=np.float32)


def _preprocess_signal(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    if samples.size == 0:
        return samples

    normalized = librosa.util.normalize(samples)
    trimmed, _ = librosa.effects.trim(normalized, top_db=30)

    if trimmed.size >= max(int(sample_rate * 0.5), 1):
        return trimmed.astype(np.float32)

    return normalized.astype(np.float32)


def _window_generator(signal: np.ndarray, sample_rate: int, window_seconds: float):
    window_size = max(int(sample_rate * window_seconds), sample_rate)
    hop_size = window_size

    start = 0
    while start < signal.size:
        end = min(start + window_size, signal.size)
        window = signal[start:end]

        if window.size < sample_rate:
            break

        yield window, start / sample_rate, end / sample_rate
        start += hop_size


def _extract_window_features(window: np.ndarray, sample_rate: int, mfcc_coefficients: int) -> tuple[np.ndarray, float]:
    mfcc = librosa.feature.mfcc(
        y=window,
        sr=sample_rate,
        n_mfcc=mfcc_coefficients,
        n_fft=512,
        hop_length=160,
    )
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)
    feature_vector = np.concatenate([mfcc_mean, mfcc_std]).astype(np.float32)

    rms = float(np.mean(librosa.feature.rms(y=window, frame_length=512, hop_length=160)))
    rms_db = float(librosa.amplitude_to_db(np.array([max(rms, 1e-6)]), ref=1.0)[0])

    return feature_vector, rms_db


def build_session_audio_batch(
    session_id: str,
    fragment_root: Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    mfcc_coefficients: int = DEFAULT_MFCC_COEFFICIENTS,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> SessionAudioBatch:
    session_dir = fragment_root / session_id
    if not session_dir.exists():
        return SessionAudioBatch(
            session_id=session_id,
            sample_rate=sample_rate,
            mfcc_coefficients=mfcc_coefficients,
            fragment_paths=[],
            windows=[],
            duration_seconds=0.0,
            mean_rms_db=None,
        )

    fragment_paths = sorted(
        [path for path in session_dir.iterdir() if path.is_file() and _is_audio_fragment(path)],
        key=lambda path: path.name,
    )

    preprocessed_chunks: list[np.ndarray] = []
    for fragment_path in fragment_paths:
        signal = _load_fragment_signal(fragment_path=fragment_path, sample_rate=sample_rate)
        if signal is None:
            continue

        cleaned_signal = _preprocess_signal(signal, sample_rate=sample_rate)
        if cleaned_signal.size < sample_rate:
            continue

        preprocessed_chunks.append(cleaned_signal)

    if not preprocessed_chunks:
        return SessionAudioBatch(
            session_id=session_id,
            sample_rate=sample_rate,
            mfcc_coefficients=mfcc_coefficients,
            fragment_paths=fragment_paths,
            windows=[],
            duration_seconds=0.0,
            mean_rms_db=None,
        )

    merged_signal = np.concatenate(preprocessed_chunks)
    duration_seconds = float(merged_signal.size / sample_rate)

    windows: list[SessionAudioWindow] = []
    rms_values: list[float] = []

    for index, (window, start_second, end_second) in enumerate(
        _window_generator(merged_signal, sample_rate=sample_rate, window_seconds=window_seconds)
    ):
        feature_vector, rms_db = _extract_window_features(
            window=window,
            sample_rate=sample_rate,
            mfcc_coefficients=mfcc_coefficients,
        )
        windows.append(
            SessionAudioWindow(
                window_index=index,
                start_second=round(start_second, 3),
                end_second=round(end_second, 3),
                rms_db=rms_db,
                feature_vector=feature_vector,
            )
        )
        rms_values.append(rms_db)

    mean_rms_db = float(np.mean(rms_values)) if rms_values else None

    return SessionAudioBatch(
        session_id=session_id,
        sample_rate=sample_rate,
        mfcc_coefficients=mfcc_coefficients,
        fragment_paths=fragment_paths,
        windows=windows,
        duration_seconds=duration_seconds,
        mean_rms_db=mean_rms_db,
    )


def cleanup_session_fragments(session_id: str, fragment_root: Path) -> None:
    session_dir = fragment_root / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
