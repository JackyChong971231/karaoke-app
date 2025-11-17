import os
import time
import sys
from yt_dlp import YoutubeDL
from pydub import AudioSegment
import vlc
import pygame
import socket
import qrcode

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QComboBox
)
from PySide6.QtCore import QTimer, Qt, Signal, QPoint
from PySide6.QtWidgets import QStackedLayout
from PySide6.QtGui import QPixmap

from processor.audio_mixer import AudioMixer

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def generate_qr_pixmap(port=5005):
    ip = get_local_ip()
    url = f"http://{ip}:{port}/remote"

    # Generate QR
    qr_img = qrcode.make(url)
    qr_path = "remote_qr.png"
    qr_img.save(qr_path)

    # Load into PySide pixmap
    pix = QPixmap(qr_path)
    return pix

class KaraokePlayer(QWidget):
    finished = Signal()

    def __init__(self, instrumental_path, lyrics_segments, vocal_path=None, video_path=None, video_url=None):
        super().__init__()
        pygame.mixer.init()
        self.instrumental_path = instrumental_path
        self.vocal_path = vocal_path
        self.lyrics_segments = lyrics_segments
        self.video_path = video_path
        self.video_url = video_url

        self.playing = False
        self.vocal_enabled = False
        self.start_time = None

        # VLC player setup
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        self._is_dragging = False
        self._drag_pos = QPoint()

        # UI setup
        self._setup_ui()
        self.audio_mixer = AudioMixer()
        self._prepare_audio_files()

        # Populate dropdown with input devices
        devices = self.audio_mixer.get_input_devices()
        for idx, name in devices.items():
            self.device_dropdown.addItem(name, idx)

    def _toggle_borderless(self):
        if self.isFullScreen():
            # Switch to normal window with borders and Windows taskbar
            self.setWindowFlags(Qt.Window)  # normal window with title bar
            self.showNormal()
            self.border_toggle_btn.setText('Fullscreen')
        else:
            # Switch to borderless full-screen
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.showFullScreen()
            self.border_toggle_btn.setText('Window Size')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Only start dragging if clicked on control panel
            if self.control_panel.underMouse():
                self._is_dragging = True
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False

    def update_next_song_label(self, queue):
        if queue:
            next_song = queue[0]
            title = next_song.get("title", "Unknown")
            artist = next_song.get("artist", "")
            self.next_song_label.setText(f"Next: {artist} - {title}")
        else:
            self.next_song_label.setText("Next: (none)")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep QR code at top-right of video frame
        self.qr_overlay.move(
            self.video_frame.width() - self.qr_overlay.width() - 10,
            10
        )

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    def _setup_ui(self):
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("Karaoke Player (Qt Edition)")
        self.setGeometry(200, 200, 1280, 720)  # large window for TV
        self.setStyleSheet("background-color: black;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Control panel (top) ---
        self.control_panel = QFrame(self)
        self.control_panel.setFixedHeight(60)
        self.control_panel.setStyleSheet("background-color: rgba(0,0,0,150);")

        control_layout = QHBoxLayout(self.control_panel)
        control_layout.setContentsMargins(10, 10, 10, 10)
        control_layout.setSpacing(10)

        control_btn_style = """
            font-size: 16px;
            padding: 8px;
            background-color: rgba(50, 50, 50, 180);
            color: white;
            border-radius: 5px;
        """

        # Buttons
        self.pause_button = QPushButton("Pause", self.control_panel)
        self.pause_button.setStyleSheet(control_btn_style)
        self.pause_button.setFixedSize(100, 40)
        self.pause_button.clicked.connect(self._toggle_pause)
        control_layout.addWidget(self.pause_button)

        self.toggle_button = QPushButton("Enable Vocal", self.control_panel)
        self.toggle_button.setStyleSheet(control_btn_style)
        self.toggle_button.setFixedSize(150, 40)
        self.toggle_button.clicked.connect(self._toggle_vocal)
        control_layout.addWidget(self.toggle_button)

        self.skip_button = QPushButton("Skip", self.control_panel)
        self.skip_button.setStyleSheet(control_btn_style)
        self.skip_button.setFixedSize(100, 40)
        self.skip_button.clicked.connect(self.skip)
        control_layout.addWidget(self.skip_button)

        exit_btn = QPushButton("Exit", self.control_panel)
        exit_btn.setStyleSheet(control_btn_style)
        exit_btn.setFixedSize(100, 40)
        exit_btn.clicked.connect(self.close)
        control_layout.addWidget(exit_btn)

        self.border_toggle_btn = QPushButton("Fullscreen", self.control_panel)
        self.border_toggle_btn.setStyleSheet(control_btn_style)
        self.border_toggle_btn.setFixedSize(150, 40)
        self.border_toggle_btn.clicked.connect(self._toggle_borderless)
        control_layout.addWidget(self.border_toggle_btn)

        # ---- Audio Input Device Selector ----
        self.device_dropdown = QComboBox(self.control_panel)
        self.device_dropdown.setStyleSheet("""
            font-size: 16px;
            padding: 5px;
            background-color: rgba(40, 40, 40, 200);
            color: white;
            border-radius: 5px;
        """)
        control_layout.addWidget(self.device_dropdown)

        self.device_dropdown.addItem("Select Input Device...")
        self.device_dropdown.currentIndexChanged.connect(self._on_device_selected)

        control_layout.addStretch()
        main_layout.addWidget(self.control_panel)

        # --- Next Song Label ---
        self.next_song_label = QLabel("Next: (none)", self.control_panel)
        self.next_song_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        self.next_song_label.setContentsMargins(30, 0, 30, 0)
        main_layout.addWidget(self.next_song_label)

        # --- Video container (flexible) ---
        self.video_container = QFrame(self)
        self.video_container.setStyleSheet("background-color: black;")
        self.video_container.setLayout(None)  # free positioning for QR overlay
        main_layout.addWidget(self.video_container, stretch=1)

        # Video frame inside container
        self.video_frame = QFrame(self.video_container)
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setGeometry(0, 0, 1280, 720)  # fills container initially

        # Floating QR code overlay
        self.qr_overlay = QLabel(self.video_container)
        pixmap = generate_qr_pixmap(port=5005)
        self.qr_overlay.setPixmap(pixmap.scaled(120, 120))
        self.qr_overlay.setStyleSheet("background: transparent;")
        self.qr_overlay.setFixedSize(120, 120)
        self.qr_overlay.raise_()
        self.qr_overlay.move(self.video_container.width() - self.qr_overlay.width() - 10, 10)

        # --- Lyrics container (bottom, fixed height) ---
        lyrics_container = QFrame(self)
        lyrics_container.setFixedHeight(130)
        lyrics_container.setStyleSheet("background-color: rgba(0,0,0,100);")
        lyrics_layout = QVBoxLayout(lyrics_container)
        lyrics_layout.setContentsMargins(5, 5, 5, 5)
        lyrics_layout.setSpacing(20)

        self.lyrics_top_left = QLabel("", lyrics_container)
        self.lyrics_top_left.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lyrics_top_left.setStyleSheet("color: white; font-size: 36px;")
        self.lyrics_top_left.setContentsMargins(30, 0, 30, 0)
        lyrics_layout.addWidget(self.lyrics_top_left)

        self.lyrics_bottom_right = QLabel("", lyrics_container)
        self.lyrics_bottom_right.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.lyrics_bottom_right.setStyleSheet("color: white; font-size: 36px;")
        self.lyrics_bottom_right.setContentsMargins(30, 0, 30, 0)
        lyrics_layout.addWidget(self.lyrics_bottom_right)

        main_layout.addWidget(lyrics_container)
        main_layout.setContentsMargins(0, 0, 0, 30)

        self.setLayout(main_layout)

        # Timer for lyrics sync
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_lyrics_sync)

        # Internal state
        self.labels = [self.lyrics_bottom_right, self.lyrics_top_left]
        self.current_index = -1
        self.next_index = 0
        self.current_label = 0

        # --- Keep QR at top-right on resize ---
        def resizeEvent(event):
            super(self.__class__, self).resizeEvent(event)
            # Resize video frame to container
            self.video_frame.setGeometry(0, 0, self.video_container.width(), self.video_container.height())
            # Keep QR top-right
            self.qr_overlay.move(self.video_container.width() - self.qr_overlay.width() - 10, 10)

        self.resizeEvent = resizeEvent


    def _on_device_selected(self, index):
        if index <= 0:
            return  # ignore placeholder "Select..."

        device_index = self.device_dropdown.currentData()
        print(f"🎤 Selected input device index: {device_index}")

        # Call AudioMixer live loopback
        self.audio_mixer.play_input_device(device_index, 3)





    # ------------------------------------------------------------
    # Audio & Video
    # ------------------------------------------------------------
    def load_song(self, instrumental_path, lyrics_segments, vocal_path=None, video_url=None):
        """Load a new song into the existing player without reopening the window."""
        # Stop current playback and reset internal lyric state
        self.stop()

        self.instrumental_path = instrumental_path
        self.vocal_path = vocal_path
        self.lyrics_segments = lyrics_segments or []
        self.video_url = video_url

        # Reset lyric indices so playback starts from the beginning
        self.current_index = -1
        self.next_index = 0
        self.current_label = 0

        # Prefill first two lines if available so UI shows something quickly
        if len(self.lyrics_segments) > 0:
            self.lyrics_top_left.setText(self.lyrics_segments[0]["text"])
        else:
            self.lyrics_top_left.setText("")
        if len(self.lyrics_segments) > 1:
            self.lyrics_bottom_right.setText(self.lyrics_segments[1]["text"])
        else:
            self.lyrics_bottom_right.setText("")

        self._prepare_audio_files()
        self.start()  # Start playing new song

    def _prepare_audio_files(self):
        # Use AudioMixer to load files
        if self.instrumental_path:
            self.audio_mixer.load_instrumental(self.instrumental_path)
        if self.vocal_path:
            self.audio_mixer.load_vocals(self.vocal_path)

        # --- Audio playback using AudioMixer ---
        if self.instrumental_path:
            self.audio_mixer.play()
            if not self.vocal_enabled:
                self.audio_mixer.set_vocal_volume(0.0)

    def _download_video(self):
        if not self.video_url:
            return None
        try:
            import os
            from yt_dlp import YoutubeDL

            # derive folder path from audio file
            if hasattr(self, "audio_path") and self.audio_path:
                folder = os.path.dirname(self.audio_path)
            elif hasattr(self, "instrumental_path") and self.instrumental_path:
                folder = os.path.dirname(self.instrumental_path)
            else:
                folder = "./karaoke_data"

            os.makedirs(folder, exist_ok=True)

            # construct video path
            self.video_path = os.path.join(folder, "video.mp4")

            # skip download if already exists
            if os.path.exists(self.video_path):
                print(f"🎬 Video already exists at {self.video_path}")
                return self.video_path

            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
                "outtmpl": self.video_path,
                "quiet": True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.video_url])

            print(f"✅ Video downloaded: {self.video_path}")
            return self.video_path

        except Exception as e:
            print(f"❌ Failed to download video: {e}")
            return None

    def _play_media(self):
        # Reset lyrics
        for lbl in self.labels:
            lbl.setText("")

        # Play audio using AudioMixer
        self.audio_mixer.play()
        if not self.vocal_enabled:
            self.audio_mixer.set_vocal_volume(0.0)

        # Start VLC video
        if self.video_path and os.path.exists(self.video_path):
            media = self.instance.media_new(self.video_path)
            self.player.set_media(media)
            win_id = int(self.video_frame.winId())
            if sys.platform.startswith("linux"):
                self.player.set_xwindow(win_id)
            elif sys.platform == "win32":
                self.player.set_hwnd(win_id)
            elif sys.platform == "darwin":
                self.player.set_nsobject(win_id)

            self.player.audio_set_mute(True)
            self.player.play()

            # Wait for video to actually start
            start_wait = time.time()
            while not self.player.is_playing() and (time.time() - start_wait) < 1.0:
                time.sleep(0.01)

        # Record wall-clock start time for syncing lyrics
        self.start_time = time.time()
        self.playing = True
        self.timer.start(50)  # update lyrics every 50ms

    # ------------------------------------------------------------
    # Lyrics + Controls
    # ------------------------------------------------------------
    def _toggle_vocal(self):
        if not self.vocal_path:
            print("⚠️ No vocal track available.")
            return

        self.vocal_enabled = not self.vocal_enabled
        self.toggle_button.setText("Disable Vocal" if self.vocal_enabled else "Enable Vocal")
        self.audio_mixer.set_vocal_volume(1.0 if self.vocal_enabled else 0.0)

    def _toggle_pause(self):
        if not self.playing:
            return

        if not self.audio_mixer.paused:
            # Currently playing → pause
            self.audio_mixer.pause()
            self.player.pause()
            self.pause_button.setText("Resume")
            return 0
        else:
            # Currently paused → resume
            self.audio_mixer.resume()
            self.player.play()
            self.pause_button.setText("Pause")
            return 1

    def skip(self):
        """Stop current playback immediately."""
        if not self.playing:
            return

        # Stop audio
        try:
            import pygame
            pygame.mixer.stop()
        except Exception:
            pass

        # Stop video
        if self.player.is_playing():
            self.player.stop()

        # Clear lyrics
        for lbl in self.labels:
            lbl.setText("")

        # Stop timer
        self.timer.stop()
        self.playing = False

        # Emit finished so main GUI knows to play next song
        self.finished.emit()

    def _update_lyrics_sync(self):
        if not self.playing:
            self.timer.stop()
            return

        # Use video time if available, fallback to AudioMixer position
        if self.video_path and self.player.is_playing():
            elapsed = self.player.get_time() / 1000.0  # VLC time is in milliseconds
        else:
            elapsed = self.audio_mixer.get_position()  # you may need to implement this if not already

        # Update lyrics according to current elapsed time
        while self.next_index < len(self.lyrics_segments) and elapsed >= self.lyrics_segments[self.next_index]["start"]:
            seg = self.lyrics_segments[self.next_index]

            # Swap labels
            self.current_label = 1 - self.current_label
            self.labels[self.current_label].setText(seg["text"])

            # Prefill the next line if exists
            next_next_index = self.next_index + 1
            if next_next_index < len(self.lyrics_segments):
                self.labels[1 - self.current_label].setText(
                    self.lyrics_segments[next_next_index]["text"]
                )
            else:
                self.labels[1 - self.current_label].setText("")

            self.current_index = self.next_index
            self.next_index += 1

        # Stop when audio finishes
        if not self.audio_mixer.is_playing() and (not self.video_path or not self.player.is_playing()):
            self.timer.stop()
            self.playing = False
            for lbl in self.labels:
                lbl.setText("")
            self.finished.emit()



    # ------------------------------------------------------------
    # Public start
    # ------------------------------------------------------------
    def start(self):
        if self.video_url:
            self._download_video()
        self._play_media()
        self.show()

    def stop(self):
        self.audio_mixer.stop()
        if self.player.is_playing():
            self.player.stop()
        self.timer.stop()
        self.playing = False
        self.lyrics_top_left.setText("")
        self.lyrics_bottom_right.setText("")

# ------------------------------------------------------------
# Example usage
# ------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    test_url = "https://www.youtube.com/watch?v=UwuAPyOImoI"
    song_dir = "./karaoke_data/BIGBANG_TAEYANG - 눈,코,입 (EYES, NOSE, LIPS) M_V"
    instrumental = f"{song_dir}/instrumental.wav"
    vocal = f"{song_dir}/vocals.wav"
    lrc_path = f"{song_dir}/vocals.wav.lrc"

    segments = []
    if os.path.exists(lrc_path):
        with open(lrc_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("["):
                    time_part, text = line.strip().split("]", 1)
                    min_sec = time_part[1:].split(":")
                    start = float(min_sec[0]) * 60 + float(min_sec[1])
                    segments.append({"start": start, "end": start + 5.0, "text": text})
    else:
        segments = [
            {"start": 0.0, "end": 5.0, "text": "First line of lyrics"},
            {"start": 5.0, "end": 10.0, "text": "Second line of lyrics"},
            {"start": 10.0, "end": 15.0, "text": "Third line of lyrics"},
        ]

    player = KaraokePlayer(instrumental, segments, vocal_path=vocal, video_url=test_url)
    player.start()

    sys.exit(app.exec())
