# processor/vocal_remover.py

import os
import sys
import subprocess
import shutil
from processor.convert_to_wav import convert_to_wav
from cache.cache_manager import CacheManager

def safe_name(name: str) -> str:
    """Convert string to ASCII-safe string for Windows paths."""
    return "".join(c if c.isalnum() else "_" for c in name)

class VocalRemover:
    def __init__(self):
        self.cache = CacheManager()

    def remove_vocals(self, input_path: str, title: str, artist: str):
        """
        Uses Demucs to create instrumental (no vocals) and vocals-only tracks.
        Saves output under karaoke_data/<artist>_<title>/.
        Returns tuple: (instrumental_path, vocals_path)
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Convert input to WAV first
        safe_wav_path, base_name = convert_to_wav(input_path)

        # Prepare target song directory
        song_dir = self.cache.get_song_dir(title, artist)
        song_dir.mkdir(parents=True, exist_ok=True)

        print(f"🎧 Removing vocals for '{title}' by '{artist}'")
        print(f"📂 Output folder: {song_dir}")

        try:
            # Run Demucs
            subprocess.run(
                [
                    sys.executable, "-m", "demucs",
                    "--two-stems", "vocals",
                    safe_wav_path,
                    "-o", str(song_dir)
                ],
                check=True
            )

            # Demucs output path pattern: <song_dir>/htdemucs/<filename>/
            model_folder = song_dir / "htdemucs" / safe_name(base_name)
            instrumental_path = model_folder / "no_vocals.wav"
            vocals_path = model_folder / "vocals.wav"

            # Move to top-level of song_dir
            final_instrumental = song_dir / "instrumental.wav"
            final_vocals = song_dir / "vocals.wav"

            if instrumental_path.exists():
                os.replace(instrumental_path, final_instrumental)
            if vocals_path.exists():
                os.replace(vocals_path, final_vocals)

            # Clean up temporary Demucs folder
            shutil.rmtree(song_dir / "htdemucs", ignore_errors=True)

            print(f"✅ Saved instrumental: {final_instrumental}")
            print(f"✅ Saved vocals: {final_vocals}")

            return str(final_instrumental), str(final_vocals)

        except subprocess.CalledProcessError as e:
            print(f"❌ Vocal removal failed: {e}")
            return None, None
