import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QMessageBox, QSplitter, QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont

from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer
from processor.worker import ProcessWorker
from cache.cache_manager import CacheManager

from remote.server import RemoteServer

import json

import re

def sanitize_filename(name: str) -> str:
    """
    Remove characters that Windows does not allow in file/folder names.
    Also strip trailing dots/spaces and collapse double spaces.
    """
    # Remove forbidden characters
    name = re.sub(r'[\\/:*?"<>|]', '', name)

    # Optional: remove weird control characters
    name = ''.join(c for c in name if c.isprintable())

    # Strip trailing dot/space (Windows does not allow)
    name = name.rstrip('. ')

    # Prevent empty folder names
    if not name:
        name = "untitled"

    return name


class QueueItemWidget(QWidget):
    removed = Signal(int)  # emit row index when delete button is pressed
    moved_to_top = Signal(int)    # NEW SIGNAL

    def __init__(self, title: str, index: int):
        super().__init__()
        self.index = index

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(10)

        # --- Delete Button ---
        self.delete_btn = QPushButton("Delete")
        font = QFont()
        font.setPointSize(14)  # Emoji size
        self.delete_btn.setFont(font)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: gray;
                border: none;
            }
            QPushButton:hover {
                background-color: darkgray;
            }
        """)

        # --- NEW Top Up Button ---
        self.top_btn = QPushButton("Top")
        self.top_btn.setStyleSheet("""
            QPushButton {
                background-color: #5A5;
                border: none;
            }
            QPushButton:hover {
                background-color: #6D6;
            }
        """)
        self.top_btn.clicked.connect(self._on_top)
        layout.addWidget(self.top_btn)

        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        # --- Label ---
        self.label = QLabel(title)
        self.label.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(self.label, stretch=1)


        self.setLayout(layout)

    def _on_delete(self):
        self.removed.emit(self.index)

    def _on_top(self):
        self.moved_to_top.emit(self.index)

# -------------------------
# Main App (Qt)
# -------------------------
class KaraokeAppQt(QWidget):
    queue_changed = Signal(list)
    add_song_signal = Signal(str, str, str, str)  # url, user, title, artist

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎤 Karaoke App (Qt Edition)")
        self.resize(1000, 700)

        # --- Default folder --- 
        self.program_folder = Path.cwd()  # default to current folder
        self.cache_folder = self.program_folder / "karaoke_data"
        self.cache_folder.mkdir(exist_ok=True, parents=True)
        global SAVE_FILE
        SAVE_FILE = self.program_folder / "Karaoke_state.json"

        self.searcher = YouTubeSearcher()
        self.downloader = YouTubeDownloader()
        self.cache = CacheManager()
        self.worker = None
        self.player_window = None

        # Queue variables
        self.queue = []
        self.queue_changed.connect(self.update_next_song_label)
        self.queue_changed.connect(lambda _: self.save_state())  # Auto-save on any queue change
        self.next_worker = None
        self.prepared_next = None
        self.current_song = None

        self._setup_ui()
        self.refresh_cache_list()

        self.remote_server = RemoteServer(self)
        self.remote_server.start()

        self.add_song_signal.connect(self.queue_song_from_url)
        self.load_state()

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

        self.select_folder_btn = QPushButton("Select Folder")
        self.open_btn = QPushButton("Open Player")
        self.pause_btn = QPushButton("⏸ Pause")
        self.stop_btn = QPushButton("⏹ Stop")
        self.skip_btn = QPushButton("⏭ Skip")
        self.select_folder_btn.clicked.connect(self.choose_program_folder)
        self.open_btn.clicked.connect(self.open_player_window)
        self.pause_btn.clicked.connect(self.pause_song)
        self.stop_btn.clicked.connect(self.stop_song)
        self.skip_btn.clicked.connect(self.skip_song)

        for btn in (self.select_folder_btn, self.open_btn, self.pause_btn, self.stop_btn, self.skip_btn):
            controls.addWidget(btn)

        self.queue_btn = QPushButton("➕ Queue Song")
        self.queue_btn.clicked.connect(self.queue_song)
        controls.addWidget(self.queue_btn)

        self.status_label = QLabel("Ready")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        # --- Next Up Section (Queue + Finished Songs) ---
        next_up_label = QLabel("Next Up")
        next_up_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFF; margin-top: 10px;")
        layout.addWidget(next_up_label)

        # Horizontal layout for Queue and Finished Songs
        queue_finished_layout = QHBoxLayout()
        queue_finished_layout.setSpacing(16)

        # Queue column
        queue_layout = QVBoxLayout()
        queue_label = QLabel("Queue")
        queue_layout.addWidget(queue_label)
        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet("""
            QListWidget {
                background-color: #111;
                color: white;
                border: 1px solid #333;
                border-radius: 6px;
            }
        """)
        queue_layout.addWidget(self.queue_list)
        queue_finished_layout.addLayout(queue_layout)

        # Finished Songs column
        finished_layout = QVBoxLayout()
        finished_label = QLabel("Finished Songs")
        finished_layout.addWidget(finished_label)
        self.finished_list = QListWidget()
        self.finished_list.setStyleSheet("""
            QListWidget {
                background-color: #111;
                color: #888;
                border: 1px solid #333;
                border-radius: 6px;
            }
        """)
        finished_layout.addWidget(self.finished_list)
        queue_finished_layout.addLayout(finished_layout)

        # Add horizontal layout to main layout
        layout.addLayout(queue_finished_layout, stretch=1)

    # -------------------------
    # Initial File loading
    # -------------------------
    def save_state(self):
        """Save current queue and finished songs to a JSON file."""
        try:
            finished_songs = [self.finished_list.item(i).text() for i in range(self.finished_list.count())]
            data = {
                "queue": self.queue,
                "finished": finished_songs
            }
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.status_label.setText("State saved.")
        except Exception as e:
            print(f"Failed to save state: {e}")

    def load_state(self):
        """Load queue and finished songs from JSON file."""
        if not SAVE_FILE.exists():
            return
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Load queue
            self.queue = data.get("queue", [])
            self._rebuild_rotated_queue()
            # Load finished
            self.finished_list.clear()
            for song_text in data.get("finished", []):
                self.finished_list.addItem(song_text)
            self.status_label.setText("State loaded.")
        except Exception as e:
            print(f"Failed to load state: {e}")

    def choose_program_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Program Folder", str(self.program_folder))
        if folder:
            self.program_folder = Path(folder)
            self.cache_folder = self.program_folder / "karaoke_data"
            self.cache_folder.mkdir(exist_ok=True, parents=True)
            self.cache.BASE_DIR = self.cache_folder

            global SAVE_FILE
            SAVE_FILE = self.program_folder / "Karaoke_state.json"

            # Reload everything
            self.refresh_cache_list()
            self.load_state()
            self.status_label.setText(f"Loaded folder: {self.program_folder}")


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
        if not hasattr(self, "current_selected") or not self.current_selected:
            QMessageBox.warning(self, "Warning", "No song selected to queue.")
            return

        song = dict(self.current_selected)
        song['title'] = sanitize_filename(song['title'])
        song['artist'] = sanitize_filename(song['artist'])
        self._add_song_to_queue(song)

    def queue_song_from_url(self, url, user, title, artist):
        """
        Queue a song using only a YouTube URL. Used by the web remote.
        """

        song_obj = {
            "url": url,
            "title": sanitize_filename(title),
            "artist": sanitize_filename(artist),
            "queued_by": user
        }

        # push into main queue system
        self._add_song_to_queue(song_obj)

    def _add_song_to_queue(self, song: dict):
        """Internal helper: add song and recalc user rotation order."""
        # Append raw song
        self.queue.append(song)
        self._rebuild_rotated_queue()
        self.status_label.setText(f"Queued: {song.get('title', '')}")
        self.queue_changed.emit(self.queue)

        # If first song in the rotated queue, prepare immediately
        if not self.next_worker and len(self.queue) == 1:
            self._prepare_next_song()


    def update_next_song_label(self):
        """Update the player window's next song label to the first song in queue."""
        if self.player_window and hasattr(self.player_window, "next_song_label"):
            if self.queue:
                next_song = self.queue[0]
                self.player_window.next_song_label.setText(
                    f"Next: 🎤: {next_song.get("queued_by", '')} - {next_song.get('title', '')} - {next_song.get('artist', '')}"
                )
            else:
                self.player_window.next_song_label.setText("Next: None")


    def on_result_double_click(self, item):
        """When user double-clicks a search result, queue it."""
        idx = self.results_list.row(item)
        if 0 <= idx < len(self.results):
            self.current_selected = self.results[idx]
            self.current_selected['queued_by'] = 'Unknown'
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
                        "queued_by": 'Unknown'
                    }
                    self.queue_song()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load cache: {e}")

    def _rebuild_rotated_queue(self):
        """Rebuild the queue in user rotation order and update UI."""
        # Group songs by user
        user_dict = {}
        for song in self.queue:
            user = song.get("queued_by", "unknown")
            user_dict.setdefault(user, []).append(song)

        # Rotate round-robin between users
        rotated = []
        while any(user_dict.values()):
            for user, songs in list(user_dict.items()):
                if songs:
                    rotated.append(songs.pop(0))
                if not songs:
                    del user_dict[user]

        # Update self.queue to rotated order
        self.queue = rotated

        # Update UI
        self.queue_list.clear()
        for i, song in enumerate(self.queue):
            label_text = f"{song.get('title', '')} - {song.get('artist', '')}"
            if song.get("queued_by"):
                label_text = f"🎤 {song['queued_by']} - " + label_text
            item_widget = QueueItemWidget(label_text, i)
            item_widget.removed.connect(self.remove_queue_item)
            item_widget.moved_to_top.connect(self.move_queue_item_to_top)
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            self.queue_list.addItem(list_item)
            self.queue_list.setItemWidget(list_item, item_widget)

    def _rebuild_queue_ui_only(self):
        """Rebuild the queue UI without modifying queue order."""
        self.queue_list.clear()

        for i, song in enumerate(self.queue):
            label_text = f"{song.get('title', '')} - {song.get('artist', '')}"
            if song.get("queued_by"):
                label_text = f"🎤 {song['queued_by']} - " + label_text

            item_widget = QueueItemWidget(label_text, i)
            item_widget.removed.connect(self.remove_queue_item)
            item_widget.moved_to_top.connect(self.move_queue_item_to_top)

            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            self.queue_list.addItem(list_item)
            self.queue_list.setItemWidget(list_item, item_widget)

    def move_queue_item_to_top(self, index):
        """Force this song to be the next in queue."""
        if 0 <= index < len(self.queue):
            song = self.queue.pop(index)
            self.queue.insert(0, song)

            self.status_label.setText(
                f"Moved to top: {song.get('title', '')}"
            )

            # Rebuild UI (DO NOT apply user-rotation logic here)
            self._rebuild_queue_ui_only()

            # Save & notify
            self.queue_changed.emit(self.queue)

            # Prepare next song immediately (optional)
            self._prepare_next_song()


    def remove_queue_item(self, index):
        """Remove a queue item and recalc rotation."""
        if 0 <= index < len(self.queue):
            del self.queue[index]
            self.status_label.setText("Removed song from queue")
            self._rebuild_rotated_queue()
            self.queue_changed.emit(self.queue)

    def mark_song_finished(self):
        """
        Add a song to the finished songs list.
        `self.current_song` can be a QListWidgetItem or a dict with title/artist
        """
        if self.current_song:
            if isinstance(self.current_song, QListWidgetItem):
                text = self.current_song.text()
            else:
                # fallback if song info is dict
                text = f"🎤 {self.current_song['queued_by']} - {self.current_song.get('title', 'Unknown')} - {self.current_song.get('artist', '')}"
            
            self.finished_list.addItem(text)
            self.save_state()  # Auto-save after finishing a song

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
        self.current_song = next_song
        # self.mark_song_finished(next_song)

        # If preprocessed song is ready
        if self.prepared_next and self.prepared_next["url"] == next_song.get("url"):
            result = self.prepared_next
            self.queue.pop(0)
            self.queue_list.takeItem(0)
            self.queue_changed.emit(self.queue)
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
        self.mark_song_finished()
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
