from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
from urllib.request import urlopen

from dotenv import load_dotenv

REQUIRED_FILES = [
    "model_spo2_v3.joblib",
    "model_audio_v3.joblib",
    "scaler_spo2_v3.joblib",
    "scaler_audio_v3.joblib",
    "metadata_v3.json",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    with urlopen(url) as response:
        payload = response.read()
    target.write_bytes(payload)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")

    model_dir = Path(os.getenv("ML_V3_MODEL_DIR", str(repo_root / "ml" / "models"))).resolve()
    base_url = os.getenv("ML_V3_MODELS_BASE_URL", "").rstrip("/")

    if not base_url:
        print("ERROR: ML_V3_MODELS_BASE_URL no está configurado en .env")
        print("Ejemplo: ML_V3_MODELS_BASE_URL=https://tu-bucket.s3.amazonaws.com/asap/v3")
        return 1

    model_dir.mkdir(parents=True, exist_ok=True)
    print(f"Destino local: {model_dir}")

    for filename in REQUIRED_FILES:
        source = f"{base_url}/{filename}"
        target = model_dir / filename
        print(f"Descargando {source}")
        _download(source, target)
        print(f"  -> ok ({target.stat().st_size} bytes, sha256={_sha256(target)[:16]}...)")

    print("Descarga completada. Archivos requeridos disponibles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
