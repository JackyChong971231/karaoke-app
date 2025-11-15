import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QMessageBox, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont

from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer
from cache.cache_manager import CacheManager

from remote.server import RemoteServer


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

class QueueItemWidget(QWidget):
    removed = Signal(int)  # emit row index when delete button is pressed

    def __init__(self, title: str, index: int):
        super().__init__()
        self.index = index

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # --- Delete Button ---
        self.delete_btn = QPushButton("🗑️")
        font = QFont()
        font.setPointSize(18)  # Emoji size
        self.delete_btn.setFont(font)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                color: red;
            }
        """)

        # Make button fit the emoji dynamically
        size_hint = self.delete_btn.sizeHint()
        self.delete_btn.setFixedSize(size_hint.width() + 4, size_hint.height() + 4)

        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        # --- Label ---
        self.label = QLabel(title)
        self.label.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(self.label, stretch=1)


        self.setLayout(layout)

    def _on_delete(self):
        self.removed.emit(self.index)

# -------------------------
# Main App (Qt)
# -------------------------
class KaraokeAppQt(QWidget):
    queue_changed = Signal(list)

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
        self.queue_changed.connect(self.update_next_song_label)
        self.next_worker = None
        self.prepared_next = None

        self._setup_ui()
        self.refresh_cache_list()

        self.remote_server = RemoteServer(self)
        self.remote_server.start()

    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #E0E0E0;
                font-family: Segoe UI, Arial;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #1E1E1E;
                border: 1px solid #333;
                padding: 6px;
                border-radius: 6px;
                color: #EEE;
            }
            QPushButton {
                background-color: #2C2C2C;
                border: none;
                padding: 8px 14px;
                border-radius: 6px;
                color: #E0E0E0;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
            QPushButton:pressed {
                background-color: #505050;
            }
            QListWidget {
                background-color: #181818;
                border: 1px solid #333;
                border-radius: 6px;
            }
            QLabel {
                font-weight: bold;
                color: #B0B0B0;
                margin-bottom: 4px;
            }

            QScrollBar:vertical {
                background-color: grey;  /* track color */
                width: 12px;
                margin: 0px 0px 0px 0px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: white;  /* handle color */
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: grey;
                height: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background-color: white;
                min-width: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: none;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Search bar ---
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search for song or artist...")
        self.search_input.textChanged.connect(self.filter_cache_list)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.on_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        # --- Splitter: results | cache ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Search results
        left = QWidget()
        left_layout = QVBoxLayout(left)
        label_results = QLabel("Search Results")
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self.on_result_selected)
        left_layout.addWidget(label_results)
        left_layout.addWidget(self.results_list)
        splitter.addWidget(left)

        # Right: Cached songs
        right = QWidget()
        right_layout = QVBoxLayout(right)
        label_cache = QLabel("Cached Songs")
        self.cache_list = QListWidget()
        self.cache_list.itemSelectionChanged.connect(self.on_cache_selected)
        right_layout.addWidget(label_cache)

        cache_filter_layout = QHBoxLayout()


        self.cache_artist_filter = QLineEdit()
        self.cache_artist_filter.setPlaceholderText("Artist filter...")
        self.cache_artist_filter.textChanged.connect(self.filter_cache_list)

        cache_filter_layout.addWidget(self.cache_artist_filter)
        right_layout.addLayout(cache_filter_layout)

        right_layout.addWidget(self.cache_list)
        splitter.addWidget(right)

        layout.addWidget(splitter, stretch=1)
        self.results_list.itemDoubleClicked.connect(self.on_result_double_click)
        self.cache_list.itemDoubleClicked.connect(self.on_cache_double_click)

        # --- Controls ---
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.open_btn = QPushButton("Open Player")
        self.pause_btn = QPushButton("⏸ Pause")
        self.stop_btn = QPushButton("⏹ Stop")
        self.skip_btn = QPushButton("⏭ Skip")

        self.open_btn.clicked.connect(self.open_player_window)
        self.pause_btn.clicked.connect(self.pause_song)
        self.stop_btn.clicked.connect(self.stop_song)
        self.skip_btn.clicked.connect(self.skip_song)

        for btn in (self.open_btn, self.pause_btn, self.stop_btn, self.skip_btn):
            controls.addWidget(btn)

        self.queue_btn = QPushButton("➕ Queue Song")
        self.queue_btn.clicked.connect(self.queue_song)
        controls.addWidget(self.queue_btn)

        self.status_label = QLabel("Ready")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        # --- Next Up Section ---
        next_up_label = QLabel("Next Up")
        next_up_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFF; margin-top: 10px;")
        layout.addWidget(next_up_label)

        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet("""
            QListWidget {
                background-color: #111;
                color: white;
                border: 1px solid #333;
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.queue_list)

    # -------------------------
    # UI Logic
    # -------------------------
    def refresh_cache_list(self):
        self.cached_songs = []  # store dicts with title/artist
        for folder in sorted(self.cache.BASE_DIR.iterdir()):
            if not folder.is_dir():
                continue
            meta = folder / "meta.json"
            if meta.exists():
                try:
                    info = json.loads(meta.read_text(encoding="utf-8"))
                    self.cached_songs.append(info)
                except Exception:
                    continue
        self.filter_cache_list()  # show filtered list

    def filter_cache_list(self):
        query = self.search_input.text().lower()
        self.cache_list.clear()
        for info in self.cached_songs:
            title = info.get("title", "").lower()
            artist = info.get("artist", "").lower()
            if query and query not in title and query not in artist:
                continue
            self.cache_list.addItem(f"{info['artist']} - {info['title']}")

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
        song = dict(self.current_selected)
        self.queue.append(song)

        # Create custom list item
        item_widget = QueueItemWidget(f"{song.get('artist', '')} - {song.get('title', '')}", len(self.queue) - 1)
        item_widget.removed.connect(self.remove_queue_item)

        list_item = QListWidgetItem()
        list_item.setSizeHint(item_widget.sizeHint())

        self.queue_list.addItem(list_item)
        self.queue_list.setItemWidget(list_item, item_widget)

        self.status_label.setText(f"Queued {song.get('title', '')}")

        # If nothing is being prepared yet, start preparing next
        if not self.next_worker and len(self.queue) == 1:
            self._prepare_next_song()

        self.queue_changed.emit(self.queue)  # notify

    def update_next_song_label(self):
        """Update the player window's next song label to the first song in queue."""
        if self.player_window and hasattr(self.player_window, "next_song_label"):
            if self.queue:
                next_song = self.queue[0]
                self.player_window.next_song_label.setText(
                    f"Next: {next_song.get('artist', '')} - {next_song.get('title', '')}"
                )
            else:
                self.player_window.next_song_label.setText("Next: None")


    def on_result_double_click(self, item):
        """When user double-clicks a search result, queue it."""
        idx = self.results_list.row(item)
        if 0 <= idx < len(self.results):
            self.current_selected = self.results[idx]
            self.queue_song()

    def on_cache_double_click(self, item):
        """When user double-clicks a cached song, queue it."""
        idx = self.cache_list.row(item)
        folder = sorted(self.cache.BASE_DIR.iterdir())[idx]
        meta_path = folder / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                cached = self.cache.check_existing(meta["title"], meta["artist"])
                if cached:
                    cached["url"] = meta.get("url")
                    self.current_selected = {
                        "title": meta["title"],
                        "artist": meta["artist"],
                        "url": meta.get("url"),
                        "cached": cached,
                    }
                    self.queue_song()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load cache: {e}")

    def remove_queue_item(self, index):
        """Remove a queue item when its trash button is clicked."""
        if 0 <= index < len(self.queue):
            del self.queue[index]
            self.queue_list.takeItem(index)
            self.status_label.setText("Removed song from queue")

        # Re-index remaining items so delete buttons stay correct
        for i in range(self.queue_list.count()):
            widget = self.queue_list.itemWidget(self.queue_list.item(i))
            if widget:
                widget.index = i
        self.queue_changed.emit(self.queue)  # notify


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
        """Store preprocessed result for queued song and auto-play if player is open."""
        # If 'segments' missing (cached song), generate from LRC
        if "segments" not in result or not result["segments"]:
            lrc_path = result.get("lyrics")
            segments = []
            if lrc_path and os.path.exists(lrc_path):
                with open(lrc_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("["):
                            t, text = line.strip().split("]", 1)
                            m, s = map(float, t[1:].split(":"))
                            segments.append({"start": m*60 + s, "end": m*60 + s + 5, "text": text})
            result["segments"] = segments

        self.prepared_next = result
        self.update_next_song_label()
        self.status_label.setText(f"Next song ready: {result.get('url', '')}")
        self.refresh_cache_list()
        self.next_worker = None

        if self.player_window and self.player_window.isVisible():
            self._play_next_from_queue()

    def _play_next_from_queue(self):
        if not self.queue:
            return

        if not self.player_window:
            return

        if self.player_window.playing:  # <-- check if a song is currently playing
            return  # just wait, next song will auto-play when current finishes

        next_song = self.queue[0]

        # If preprocessed song is ready
        if self.prepared_next and self.prepared_next["url"] == next_song.get("url"):
            result = self.prepared_next
            self.queue.pop(0)
            self.queue_list.takeItem(0)
            self.player_window.load_song(result["instrumental"], result["segments"], result["vocals"], result["url"])
            self.prepared_next = None
            self._prepare_next_song()
        else:
            # Song is not ready yet, start preprocessing if not already
            if not self.next_worker:
                self._prepare_next_song()

    def skip_song(self):
        if self.player_window and self.player_window.isVisible():
            self.player_window.skip()
            self.status_label.setText("Skipped to next song")

    # -------------------------
    # Player logic
    # -------------------------
    def open_player_window(self):
        if not self.player_window or not self.player_window.isVisible():
            self.player_window = KaraokePlayer(None, [], vocal_path=None)
            self.player_window.show()
            # Connect finished signal to trigger queue monitor again
            self.player_window.finished.connect(self.start_queue_monitor)
            # Start monitoring the queue
            self.start_queue_monitor()

    def start_queue_monitor(self):
        if hasattr(self, 'queue_timer') and self.queue_timer.isActive():
            self.queue_timer.stop()
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.check_queue_and_play)
        self.queue_timer.start(500)  # check every 0.5 seconds

    def check_queue_and_play(self):
        if len(self.queue) > 0:
            self.queue_timer.stop()  # stop checking while playing
            self._play_next_from_queue()

    def pause_song(self):
        if self.player_window and self.player_window.isVisible():
            onOff = self.player_window._toggle_pause()
            if onOff == 1:
                self.pause_btn.setText("Resume")
            elif onOff == 0:
                self.pause_btn.setText("Pause")

    def toggle_vocal(self):
        self.player_window._toggle_vocal()

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
