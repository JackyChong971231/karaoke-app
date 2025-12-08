from PySide6.QtCore import QThread, Signal
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from cache.cache_manager import CacheManager
from utils.filename_safety import safe_name_long


class ProcessWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)
    status = Signal(str)

    def __init__(self, selected, cache: CacheManager, program_data_folder):
        super().__init__()
        self.selected = selected
        self.cache = cache
        self.program_data_folder = program_data_folder

    def _download_video(self, video_url, song_dir):
        """Download video to the same folder as the audio, if not already present."""
        from yt_dlp import YoutubeDL
        import os

        video_path = os.path.join(song_dir, "video.mp4")

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
            title = safe_name_long(self.selected["title"])
            artist = safe_name_long(self.selected["artist"])
            url = self.selected["url"]

            cached = self.cache.check_existing(title, artist)
            if cached:
                cached["url"] = url
                # If a downloaded video is present in the song folder, include it
                song_dir = self.cache.get_song_dir(title, artist)
                video_path = song_dir / "video.mp4"
                if video_path.exists():
                    cached["video"] = str(video_path)
                else:
                    cached["video"] = None

                self.status.emit("Loaded from cache")
                self.finished.emit(cached)
                return
            
            song_dir = self.cache.get_song_dir(title, artist)
            song_dir.mkdir(parents=True, exist_ok=True)

            self.status.emit("Downloading audio...")
            downloader = YouTubeDownloader()
            audio_path = downloader.download_audio(song_dir, url)
            if not audio_path:
                raise RuntimeError("Failed to download audio")

            self.status.emit("Removing vocals...")
            remover = VocalRemover()
            instrumental_path, vocals_path = remover.remove_vocals(
                audio_path, song_dir, title, artist
            )

            self.status.emit("Transcribing lyrics...")
            lm = LyricsManager()
            segments, lrc_path = lm.transcribe(vocals_path, song_dir, title, artist)

            # --- Download video if URL provided ---
            self.status.emit("Downloading video...")
            video_path = None
            if url:
                video_path = self._download_video(url, song_dir)

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