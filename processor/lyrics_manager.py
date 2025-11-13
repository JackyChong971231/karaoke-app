# processor/lyrics_manager.py

import os
import whisper
from pathlib import Path
from cache.cache_manager import CacheManager

class LyricsManager:
    def __init__(self, model_name="medium"):
        self.model = whisper.load_model(model_name)
        self.cache = CacheManager()

    def transcribe(self, vocals_path: str, title: str, artist: str):
        """
        Transcribe the vocals (vocals.wav) and return a list of segments.
        Each segment: {"start": float, "end": float, "text": str}
        """
        if not os.path.exists(vocals_path):
            raise FileNotFoundError(f"{vocals_path} not found.")

        # Check if lyrics already exist in cache
        cached = self.cache.check_existing(title, artist)
        if cached and Path(cached["lyrics"]).exists():
            print(f"🎵 Using cached lyrics for '{title}' by '{artist}'")
            return self._load_lrc(cached["lyrics"])

        print(f"📝 Transcribing vocals for '{title}' by '{artist}'")
        result = self.model.transcribe(vocals_path)
        segments = result.get("segments", [])

        # Save .lrc in the song folder
        song_dir = self.cache.get_song_dir(title, artist)
        song_dir.mkdir(exist_ok=True)
        lrc_path = song_dir / "lyrics.lrc"
        self.save_lrc(segments, lrc_path)

        return segments

    def save_lrc(self, segments, lrc_path: str):
        """
        Save the transcription as a .lrc file (timed lyrics)
        """
        with open(lrc_path, "w", encoding="utf-8") as f:
            for seg in segments:
                start_min = int(seg["start"] // 60)
                start_sec = seg["start"] % 60
                f.write(f"[{start_min:02d}:{start_sec:05.2f}]{seg['text']}\n")
        return lrc_path

    def _load_lrc(self, lrc_path: str):
        """
        Load existing .lrc file and convert to segments list
        """
        segments = []
        with open(lrc_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("["):
                    time_part, text = line.strip().split("]", 1)
                    min_sec = time_part[1:].split(":")
                    start = float(min_sec[0]) * 60 + float(min_sec[1])
                    segments.append({"start": start, "end": start + 5.0, "text": text})  # rough 5s per line
        return segments
