import os
import whisper

class LyricsManager:
    def __init__(self, model_name="medium"):
        self.model = whisper.load_model(model_name)

    def transcribe(self, wav_path: str):
        """
        Transcribe the vocals (no-vocals.wav) and return a list of segments.
        Each segment: {"start": float, "end": float, "text": str}
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"{wav_path} not found.")

        result = self.model.transcribe(wav_path)
        return result.get("segments", [])
    
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
