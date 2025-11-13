import os
import json
from pathlib import Path
import re

class CacheManager:
    BASE_DIR = Path("karaoke_data")

    def __init__(self):
        self.BASE_DIR.mkdir(exist_ok=True)

    def _sanitize(self, name: str) -> str:
        """Sanitize song name for safe folder names."""
        return re.sub(r'[\\/*?:"<>|]', "_", name)

    def get_song_dir(self, title: str, artist: str) -> Path:
        folder_name = self._sanitize(f"{artist}_{title}")
        return self.BASE_DIR / folder_name

    def check_existing(self, title: str, artist: str):
        """Check if this song has already been processed."""
        song_dir = self.get_song_dir(title, artist)
        if not song_dir.exists():
            return None

        instrumental = song_dir / "instrumental.wav"
        vocals = song_dir / "vocals.wav"
        lyrics = song_dir / "lyrics.lrc"

        if instrumental.exists() and vocals.exists() and lyrics.exists():
            return {
                "instrumental": str(instrumental),
                "vocals": str(vocals),
                "lyrics": str(lyrics)
            }
        return None

    def save_meta(self, title: str, artist: str, url: str):
        song_dir = self.get_song_dir(title, artist)
        song_dir.mkdir(exist_ok=True)
        meta = {"title": title, "artist": artist, "url": url}
        with open(song_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
