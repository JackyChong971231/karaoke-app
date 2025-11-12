import os
import subprocess
import tempfile

def convert_to_wav(input_path: str) -> str:
    """
    Converts any audio/video input (mp4/webm/ogg) to a WAV file with ASCII-safe path.
    Returns path to WAV file.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    # ASCII-safe base name
    safe_base = "".join(c if c.isalnum() else "_" for c in base_name)
    temp_dir = tempfile.gettempdir()
    wav_path = os.path.join(temp_dir, f"{safe_base}.wav")

    # Convert using ffmpeg
    cmd = ["ffmpeg", "-y", "-i", input_path, "-ar", "44100", "-ac", "2", wav_path]
    subprocess.run(cmd, check=True)

    if not os.path.exists(wav_path):
        raise RuntimeError("Conversion failed!")

    print(f"✅ Converted to WAV: {wav_path}")
    return wav_path, safe_base
