import os
import subprocess
import tempfile
from utils.filename_safety import safe_name_long

def convert_to_wav(input_path: str) -> tuple[str, str]:
    """
    Converts any audio/video input (mp4/webm/ogg) to a WAV file with safe path.
    Returns tuple: (wav_path, safe_base_name)
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    safe_base = safe_name_long(base_name)  # truncate and remove forbidden characters

    temp_dir = tempfile.gettempdir()
    wav_path = os.path.join(temp_dir, f"{safe_base}.wav")

    # Convert using ffmpeg
    cmd = ["ffmpeg", "-y", "-i", input_path, "-ar", "44100", "-ac", "2", wav_path]
    subprocess.run(cmd, check=True)

    if not os.path.exists(wav_path):
        raise RuntimeError("Conversion failed!")

    print(f"✅ Converted to WAV: {wav_path}")
    return wav_path, safe_base
