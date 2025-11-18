import os
from pathlib import Path
import whisper
import numpy as np
import librosa
from cache.cache_manager import CacheManager

class LyricsManager:
    def __init__(self, model_name="medium"):
        self.model = whisper.load_model(model_name)
        self.cache = CacheManager()

    def transcribe(self, vocals_path: str, title: str, artist: str):
        """
        Transcribe vocals.wav and return (segments, lrc_path).
        Automatically detects first sung word and offsets timestamps.
        """
        if not os.path.exists(vocals_path):
            raise FileNotFoundError(f"{vocals_path} not found.")

        # Check cache
        cached = self.cache.check_existing(title, artist)
        if cached and Path(cached["lyrics"]).exists():
            print(f"🎵 Using cached lyrics for '{title}' by '{artist}'")
            return self._load_lrc(cached["lyrics"]), Path(cached["lyrics"])

        # Detect first non-silent frame
        y, sr = librosa.load(vocals_path, sr=44100)
        rms = librosa.feature.rms(y=y)[0]
        threshold = 0.01  # adjust if too sensitive or misses quiet vocals
        first_idx = np.argmax(rms > threshold)
        first_time = librosa.frames_to_time(first_idx, sr=sr, hop_length=512)
        print(f"Detected first vocal at {first_time:.2f} seconds")

        # Slice audio from first vocal
        y_sliced = y[int(first_time * sr):]

        # Save temporary file for Whisper
        temp_path = Path(vocals_path).parent / "vocals_trimmed.wav"
        import soundfile as sf
        sf.write(temp_path, y_sliced, sr)

        # Transcribe
        result = self.model.transcribe(
            str(temp_path),
            fp16=False,
            temperature=0.0,
            word_timestamps=False,
            no_speech_threshold=0.2
        )
        segments = result.get("segments", [])

        # Offset timestamps by first_time
        for seg in segments:
            seg["start"] += first_time
            seg["end"] += first_time

        # Save .lrc
        song_dir = self.cache.get_song_dir(title, artist)
        song_dir.mkdir(exist_ok=True)
        lrc_path = song_dir / "lyrics.lrc"
        self.save_lrc(segments, lrc_path)

        # Clean up temp file
        temp_path.unlink(missing_ok=True)

        return segments, lrc_path

    def save_lrc(self, segments, lrc_path: str):
        with open(lrc_path, "w", encoding="utf-8") as f:
            for seg in segments:
                start_min = int(seg["start"] // 60)
                start_sec = seg["start"] % 60
                f.write(f"[{start_min:02d}:{start_sec:05.2f}]{seg['text']}\n")
        return lrc_path

    def _load_lrc(self, lrc_path: str):
        segments = []
        with open(lrc_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("["):
                    time_part, text = line.strip().split("]", 1)
                    min_sec = time_part[1:].split(":")
                    start = float(min_sec[0]) * 60 + float(min_sec[1])
                    segments.append({"start": start, "end": start + 5.0, "text": text})
        return segments
