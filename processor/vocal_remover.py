import os
import subprocess
import sys
from processor.convert_to_wav import convert_to_wav

def safe_name(name: str) -> str:
    """Convert string to ASCII-safe string for Windows paths."""
    return "".join(c if c.isalnum() else "_" for c in name)

class VocalRemover:
    def __init__(self, output_dir="instrumentals"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def remove_vocals(self, input_path: str) -> str:
        """
        Uses Demucs to create instrumental (no vocals) track.
        Returns path to WAV file.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Convert input to WAV first (temp safe file)
        safe_wav_path, base_name = convert_to_wav(input_path)

        # Make output folder safe (ASCII only)
        safe_base = safe_name(base_name)
        output_folder = os.path.join(self.output_dir, safe_base)
        os.makedirs(output_folder, exist_ok=True)

        print(f"🎧 Removing vocals from: {safe_wav_path}")
        print(f"📂 Output folder: {output_folder}")

        try:
            # Run demucs using ASCII-safe paths only
            subprocess.run(
                [sys.executable, "-m", "demucs",
                 "--two-stems", "vocals",
                 safe_wav_path,
                 "-o", output_folder],
                check=True
            )

            # Demucs usually outputs to: output_folder/htdemucs/<basename>/no_vocals.wav
            instrumental_path = os.path.join(output_folder, "htdemucs", safe_base, "no_vocals.wav")

            if not os.path.exists(instrumental_path):
                # fallback to mixture.wav if no_vocals.wav not found
                instrumental_path = os.path.join(output_folder, "htdemucs", safe_base, "mixture.wav")

            print(f"✅ Instrumental created: {instrumental_path}")
            return instrumental_path

        except subprocess.CalledProcessError as e:
            print(f"❌ Vocal removal failed: {e}")
            return None
