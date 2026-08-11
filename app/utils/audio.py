import subprocess
from pathlib import Path


def convert_to_wav(input_path: str) -> str:
    input_path_obj = Path(input_path)
    output_path = str(input_path_obj.parent / f"{input_path_obj.stem}_converted.wav")

    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", output_path],
        capture_output=True,
        check=True,
    )

    return output_path
