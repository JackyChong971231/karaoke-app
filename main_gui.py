import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QLabel, QMessageBox, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread

from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer
from cache.cache_manager import CacheManager


# -------------------------
# Worker Thread
# -------------------------
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


# -------------------------
# Main App (Qt)
# -------------------------
class KaraokeAppQt(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎤 Karaoke App (Qt Edition)")
        self.resize(1000, 700)

        self.searcher = YouTubeSearcher()
        self.downloader = YouTubeDownloader()
        self.cache = CacheManager()
        self.worker = None
        self.player_window = None

        # Queue variables
        self.queue = []
        self.next_worker = None
        self.prepared_next = None

        self._setup_ui()
        self.refresh_cache_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Search bar ---
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for song or artist...")
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.on_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        # --- Splitter: results | cache ---
        splitter = QSplitter(Qt.Horizontal)

        # Search results
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Search Results"))
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self.on_result_selected)
        left_layout.addWidget(self.results_list)
        splitter.addWidget(left)

        # Cached songs
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Cached Songs"))
        self.cache_list = QListWidget()
        self.cache_list.itemSelectionChanged.connect(self.on_cache_selected)
        right_layout.addWidget(self.cache_list)
        splitter.addWidget(right)

        layout.addWidget(splitter, stretch=1)

        # --- Controls ---
        controls = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.skip_btn = QPushButton("Skip")
        self.play_btn.clicked.connect(self.play_song)
        self.pause_btn.clicked.connect(self.pause_song)
        self.stop_btn.clicked.connect(self.stop_song)
        self.skip_btn.clicked.connect(self.skip_song)
        for b in (self.play_btn, self.pause_btn, self.stop_btn, self.skip_btn):
            controls.addWidget(b)

        self.queue_btn = QPushButton("Queue Song")
        self.queue_btn.clicked.connect(self.queue_song)
        controls.addWidget(self.queue_btn)

        self.status_label = QLabel("")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        # --- Next Up Section ---
        layout.addWidget(QLabel("Next Up"))
        self.queue_list = QListWidget()
        layout.addWidget(self.queue_list)

    # -------------------------
    # UI Logic
    # -------------------------
    def refresh_cache_list(self):
        self.cache_list.clear()
        for folder in sorted(self.cache.BASE_DIR.iterdir()):
            if not folder.is_dir():
                continue
            meta = folder / "meta.json"
            if meta.exists():
                try:
                    info = json.loads(meta.read_text(encoding="utf-8"))
                    self.cache_list.addItem(f"{info['artist']} - {info['title']}")
                except Exception:
                    continue

    def on_search(self):
        q = self.search_input.text().strip()
        if not q:
            QMessageBox.warning(self, "Warning", "Enter a search term first.")
            return

        self.results_list.clear()
        self.status_label.setText("Searching...")
        QApplication.processEvents()

        try:
            self.results = self.searcher.search(q, max_results=10)
            for r in self.results:
                self.results_list.addItem(f"{r.get('artist', '')} - {r.get('title', '')} ({r.get('duration', '')})")
            self.status_label.setText(f"Found {len(self.results)} results.")
        except Exception as e:
            QMessageBox.critical(self, "Search Error", str(e))
            self.status_label.setText("Search failed")

    def on_result_selected(self):
        if not self.results_list.selectedIndexes():
            self.current_selected = None
            return
        idx = self.results_list.selectedIndexes()[0].row()
        self.current_selected = self.results[idx]

    def on_cache_selected(self):
        idxs = self.cache_list.selectedIndexes()
        if not idxs:
            self.current_selected = None
            return
        idx = idxs[0].row()
        folder = sorted(self.cache.BASE_DIR.iterdir())[idx]
        try:
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            cached = self.cache.check_existing(meta["title"], meta["artist"])
            if cached:
                cached["url"] = meta.get("url")
                self.current_selected = {
                    "title": meta["title"],
                    "artist": meta["artist"],
                    "url": meta.get("url"),
                    "cached": cached,
                }
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # -------------------------
    # Queue logic
    # -------------------------
    def queue_song(self):
        """Add selected song to queue."""
        if not hasattr(self, "current_selected") or not self.current_selected:
            QMessageBox.warning(self, "Warning", "No song selected to queue.")
            return

        # Shallow copy to avoid mutation
        self.queue.append(dict(self.current_selected))
        self.queue_list.addItem(f"{self.current_selected.get('artist', '')} - {self.current_selected.get('title', '')}")
        self.status_label.setText(f"Queued {self.current_selected.get('title', '')}")

        # If nothing is being prepared yet, start preparing next
        if not self.next_worker and len(self.queue) == 1:
            self._prepare_next_song()

    def _prepare_next_song(self):
        if not self.queue:
            self.next_worker = None
            self.prepared_next = None
            return

        next_song = self.queue[0]
        self.status_label.setText(f"Preparing next song: {next_song['title']}")

        worker = ProcessWorker(next_song, self.cache)
        worker.status.connect(lambda s: self.status_label.setText(f"[Next] {s}"))
        worker.error.connect(lambda e: QMessageBox.warning(self, "Queue Error", e))

        def on_finished(result):
            self._on_next_prepared(result)
            # safely delete worker after done
            worker.quit()
            worker.wait()
            worker.deleteLater()
            if self.next_worker is worker:
                self.next_worker = None

        worker.finished.connect(on_finished)
        self.next_worker = worker  # keep reference until done
        worker.start()


    def _on_next_prepared(self, result):
        """Store preprocessed result for queued song."""
        self.prepared_next = result
        self.status_label.setText(f"Next song ready: {result.get('url', '')}")
        self.refresh_cache_list()
        self.next_worker = None

    def _play_next_from_queue(self):
        """Play the next prepared song if available."""
        if not self.queue:
            return  # nothing to play

        next_song = self.queue.pop(0)
        self.queue_list.takeItem(0)

        # Determine if cached or preprocessed
        if "cached" in next_song:
            info = next_song["cached"]
            lrc_path = info["lyrics"]
            segments = []
            if os.path.exists(lrc_path):
                with open(lrc_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("["):
                            t, text = line.strip().split("]", 1)
                            m, s = map(float, t[1:].split(":"))
                            segments.append({"start": m*60 + s, "end": m*60 + s + 5, "text": text})
            self.player_window.load_song(info["instrumental"], segments, info["vocals"], info.get("url"))
        elif self.prepared_next and self.prepared_next["url"] == next_song.get("url"):
            result = self.prepared_next
            self.player_window.load_song(result["instrumental"], result["segments"], result["vocals"], result["url"])
            self.prepared_next = None
        else:
            # If not ready, start processing
            self._prepare_next_song()

    def skip_song(self):
        if self.player_window and self.player_window.isVisible():
            self.player_window.skip()
            self.status_label.setText("Skipped to next song")

    # -------------------------
    # Player logic
    # -------------------------
    def play_song(self):
        """Start playing songs from the queue in order."""
        # If nothing is queued and nothing is selected, warn
        if not self.queue and (not hasattr(self, "current_selected") or not self.current_selected):
            QMessageBox.warning(self, "Warning", "No song selected or queued.")
            return

        # If queue is empty, add the currently selected song
        if not self.queue and self.current_selected:
            self.queue.append(dict(self.current_selected))
            self.queue_list.addItem(f"{self.current_selected.get('artist', '')} - {self.current_selected.get('title', '')}")

        # Start playing the first song in the queue
        next_song = self.queue[0]

        # If already cached
        if "cached" in next_song:
            info = next_song["cached"]
            lrc_path = info["lyrics"]
            segments = []
            if os.path.exists(lrc_path):
                with open(lrc_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("["):
                            t, text = line.strip().split("]", 1)
                            m, s = map(float, t[1:].split(":"))
                            segments.append({"start": m * 60 + s, "end": m * 60 + s + 5, "text": text})
            self._open_player(info["instrumental"], segments, info["vocals"], info.get("url"))
            self.queue.pop(0)
            self.queue_list.takeItem(0)
            # Start preparing the next song in queue
            self._prepare_next_song()
        # If already preprocessed
        elif self.prepared_next and self.prepared_next["url"] == next_song.get("url"):
            result = self.prepared_next
            self._open_player(result["instrumental"], result["segments"], result["vocals"], result["url"])
            self.queue.pop(0)
            self.queue_list.takeItem(0)
            self.prepared_next = None
            self._prepare_next_song()
        # Otherwise, start processing the song
        else:
            self.status_label.setText("Processing song...")
            self.next_worker = ProcessWorker(next_song, self.cache)
            self.next_worker.status.connect(lambda s: self.status_label.setText(f"[Processing] {s}"))
            self.next_worker.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
            self.next_worker.finished.connect(self._on_next_song_ready)
            self.next_worker.start()

    def _on_next_song_ready(self, result):
        """Callback when the next song is processed and ready to play."""
        self.prepared_next = result
        self.play_song()  # Automatically play it



    def _on_processing_done(self, result):
        self.status_label.setText("Processing complete!")
        self._open_player(result["instrumental"], result["segments"], result["vocals"], result["url"])
        self.refresh_cache_list()

    def _open_player(self, instrumental, segments, vocal, video_url=None):
        """Open or reuse the KaraokePlayer."""
        if self.player_window and self.player_window.isVisible():
            # Reuse existing player
            self.player_window.load_song(instrumental, segments, vocal, video_url)
        else:
            # Create new player window
            self.player_window = KaraokePlayer(instrumental, segments, vocal_path=vocal, video_url=video_url)
            self.player_window.show()
            self.player_window.start()

        if not hasattr(self.player_window, "_connected_finished"):
            self.player_window.finished.connect(self._play_next_from_queue)
            self.player_window._connected_finished = True

    def pause_song(self):
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.pause()
                self.status_label.setText("Paused")
        except Exception:
            pass

    def stop_song(self):
        try:
            import pygame
            pygame.mixer.stop()
        except Exception:
            pass
        if self.player_window:
            self.player_window.close()
        self.status_label.setText("Stopped")


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = KaraokeAppQt()
    win.show()
    sys.exit(app.exec())
