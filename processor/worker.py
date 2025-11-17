from PySide6.QtCore import QThread, Signal
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from cache.cache_manager import CacheManager

class ProcessWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)
    status = Signal(str)

    def __init__(self, selected, cache: CacheManager):
        super().__init__()
        self.selected = selected
        self.cache = cache

    def _download_video(self, video_url, audio_path):
        """Download video to the same folder as the audio, if not already present."""
        from yt_dlp import YoutubeDL
        import os

        folder = os.path.dirname(audio_path)
        os.makedirs(folder, exist_ok=True)
        video_path = os.path.join(folder, "video.mp4")

        if os.path.exists(video_path):
            self.status.emit("Video already exists, skipping download")
            return video_path

        self.status.emit("Downloading video...")
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "outtmpl": video_path,
            "quiet": True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        self.status.emit("Video downloaded")
        return video_path

    def run(self):
        try:
            title = self.selected["title"]
            artist = self.selected["artist"]
            url = self.selected["url"]

            cached = self.cache.check_existing(title, artist)
            if cached:
                cached["url"] = url
                self.status.emit("Loaded from cache")
                self.finished.emit(cached)
                return

            self.status.emit("Downloading audio...")
            downloader = YouTubeDownloader()
            audio_path = downloader.download_audio(url)
            if not audio_path:
                raise RuntimeError("Failed to download audio")

            self.status.emit("Removing vocals...")
            remover = VocalRemover()
            instrumental_path, vocals_path = remover.remove_vocals(
                audio_path, title, artist
            )

            self.status.emit("Transcribing lyrics...")
            lm = LyricsManager()
            segments = lm.transcribe(vocals_path, title, artist)
            lrc_path = f"{vocals_path}.lrc"
            lm.save_lrc(segments, lrc_path)

            # --- Download video if URL provided ---
            self.status.emit("Downloading video...")
            video_path = None
            if url:
                video_path = self._download_video(url, instrumental_path)

            self.cache.save_meta(title, artist, url)

            result = {
                "instrumental": instrumental_path,
                "vocals": vocals_path,
                "lyrics": lrc_path,
                "segments": segments,
                "url": url,
                "video": video_path,
            }
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))