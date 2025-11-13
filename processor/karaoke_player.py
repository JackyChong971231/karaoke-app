import os
import time
import sys
from yt_dlp import YoutubeDL
from pydub import AudioSegment
import vlc
import pygame

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PySide6.QtCore import QTimer, Qt, Signal, QPoint
from PySide6.QtWidgets import QStackedLayout


class KaraokePlayer(QWidget):
    finished = Signal()

    def __init__(self, instrumental_path, lyrics_segments, vocal_path=None, video_path=None, video_url=None):
        super().__init__()
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
        self._prepare_audio_files()

    def _toggle_borderless(self):
        if self.isFullScreen():
            # Switch to normal window with borders and Windows taskbar
            self.setWindowFlags(Qt.Window)  # normal window with title bar
            self.showNormal()
        else:
            # Switch to borderless full-screen
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.showFullScreen()

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
        self.control_panel.setFixedHeight(60)  # fixed height
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

        # Pause button
        self.pause_button = QPushButton("Pause", self.control_panel)
        self.pause_button.setStyleSheet(control_btn_style)
        self.pause_button.setFixedSize(100, 40)
        self.pause_button.clicked.connect(self._toggle_pause)
        control_layout.addWidget(self.pause_button)

        # Toggle vocal button
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

        self.border_toggle_btn = QPushButton("Toggle Border", self.control_panel)
        self.border_toggle_btn.setStyleSheet(control_btn_style)
        self.border_toggle_btn.setFixedSize(150, 40)
        self.border_toggle_btn.clicked.connect(self._toggle_borderless)
        control_layout.addWidget(self.border_toggle_btn)

        control_layout.addStretch()
        main_layout.addWidget(self.control_panel)

        # --- Video container (flexible) ---
        self.video_container = QFrame(self)
        self.video_container.setStyleSheet("background-color: black;")
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)
        main_layout.addWidget(self.video_container, stretch=1)  # takes remaining space

        # Video frame inside container
        self.video_frame = QFrame(self.video_container)
        self.video_frame.setStyleSheet("background-color: black;")
        video_layout.addWidget(self.video_frame, stretch=1)  # fills the container

        # --- Lyrics container (bottom, fixed height) ---
        lyrics_container = QFrame(self)
        lyrics_container.setFixedHeight(100)  # adjust total height
        lyrics_container.setStyleSheet("background-color: rgba(0,0,0,100);")  # semi-transparent background
        lyrics_layout = QVBoxLayout(lyrics_container)
        lyrics_layout.setContentsMargins(5, 5, 5, 5)  # padding from edges
        lyrics_layout.setSpacing(20)

        # Top-left lyrics
        self.lyrics_top_left = QLabel("", lyrics_container)
        self.lyrics_top_left.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lyrics_top_left.setStyleSheet("color: white; font-size: 24px;")
        lyrics_layout.addWidget(self.lyrics_top_left)

        # Bottom-right lyrics
        self.lyrics_bottom_right = QLabel("", lyrics_container)
        self.lyrics_bottom_right.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.lyrics_bottom_right.setStyleSheet("color: white; font-size: 24px;")
        lyrics_layout.addWidget(self.lyrics_bottom_right)
        

        main_layout.addWidget(lyrics_container)

        self.setLayout(main_layout)

        # Timer for lyrics sync
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_lyrics_sync)

        # Internal state
        self.labels = [self.lyrics_top_left, self.lyrics_bottom_right]
        self.current_index = -1
        self.next_index = 0
        self.current_label = 0






    # ------------------------------------------------------------
    # Audio & Video
    # ------------------------------------------------------------
    def load_song(self, instrumental_path, lyrics_segments, vocal_path=None, video_url=None):
        """Load a new song into the existing player without reopening the window."""
        self.stop()  # Stop current playback

        self.instrumental_path = instrumental_path
        self.vocal_path = vocal_path
        self.lyrics_segments = lyrics_segments
        self.video_url = video_url

        self._prepare_audio_files()
        self.start()  # Start playing new song

    def _prepare_audio_files(self):
        def convert_to_pcm(input_path, output_name):
            if not input_path or not os.path.exists(input_path):
                return None
            audio = AudioSegment.from_file(input_path)
            audio = audio.set_channels(2).set_frame_rate(44100).set_sample_width(2)
            output_path = f"temp_{output_name}.wav"
            audio.export(output_path, format="wav")
            return output_path

        self.instrumental_pcm = convert_to_pcm(self.instrumental_path, "instrumental")
        self.vocal_pcm = convert_to_pcm(self.vocal_path, "vocal")

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
        """Start video and audio playback (uses local video.mp4 + instrumental/vocal audio)"""
        import os, sys, time, pygame

        # --- Reset lyrics labels & internal state for initial display ---
        if len(self.lyrics_segments) > 0:
            self.lyrics_top_left.setText(self.lyrics_segments[0]["text"])
        else:
            self.lyrics_top_left.setText("")
        if len(self.lyrics_segments) > 1:
            self.lyrics_bottom_right.setText(self.lyrics_segments[1]["text"])
        else:
            self.lyrics_bottom_right.setText("")

        self.current_index = -1
        self.next_index = 0
        self.current_label = 0

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
        # --- VLC Video Playback ---
        if self.video_path and os.path.exists(self.video_path):
            media = self.instance.media_new(self.video_path)
            self.player.set_media(media)

            # Embed VLC output in Qt video frame
            win_id = int(self.video_frame.winId())
            if sys.platform.startswith("linux"):
                self.player.set_xwindow(win_id)
            elif sys.platform == "win32":
                self.player.set_hwnd(win_id)
            elif sys.platform == "darwin":
                self.player.set_nsobject(win_id)

            # Mute video audio (we'll use our processed audio instead)
            self.player.audio_set_mute(True)
            self.player.play()

            # Wait until VLC starts
            start_wait = time.time()
            while not self.player.is_playing() and (time.time() - start_wait) < 1.5:
                time.sleep(0.01)

        else:
            print("⚠️ No video found. Skipping VLC video playback.")

        # --- Pygame Audio Playback (instrumental/vocal mix) ---
        if self.instrumental_pcm:
            pygame.mixer.init(frequency=44100, size=-16, channels=2)
            pygame.mixer.set_num_channels(2)

            instrumental_sound = pygame.mixer.Sound(self.instrumental_pcm)
            pygame.mixer.Channel(0).play(instrumental_sound)

            if self.vocal_pcm:
                vocal_sound = pygame.mixer.Sound(self.vocal_pcm)
                pygame.mixer.Channel(1).play(vocal_sound)
                if not self.vocal_enabled: pygame.mixer.Channel(1).set_volume(0.0)  # start muted

            print("🎵 Audio playback started.")
        else:
            print("⚠️ No instrumental audio found, skipping audio playback.")

        # --- Start lyric sync ---
        self.start_time = time.time()
        self.playing = True
        self.timer.start(50)  # update lyrics every 50ms

    # ------------------------------------------------------------
    # Lyrics + Controls
    # ------------------------------------------------------------
    def _toggle_vocal(self):
        if not self.vocal_pcm:
            print("⚠️ No vocal track available.")
            return

        self.vocal_enabled = not self.vocal_enabled
        self.toggle_button.setText("Disable Vocal" if self.vocal_enabled else "Enable Vocal")

        pygame.mixer.Channel(1).set_volume(1.0 if self.vocal_enabled else 0.0)

    def _toggle_pause(self):
        import pygame
        if self.playing:
            if self.player.is_playing():
                # Pause video and audio
                self.player.pause()
                pygame.mixer.pause()
                self.pause_button.setText("Resume")
            else:
                # Resume video and audio
                self.player.play()
                pygame.mixer.unpause()
                self.pause_button.setText("Pause")

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

        # Use VLC playback time instead of wall clock
        if self.player.is_playing() or self.player.get_state() in (vlc.State.Paused, vlc.State.Playing):
            elapsed = self.player.get_time() / 1000.0  # VLC returns milliseconds
        else:
            elapsed = 0

        # Check if we need to move to the next line
        if self.next_index < len(self.lyrics_segments):
            seg = self.lyrics_segments[self.next_index]
            if elapsed >= seg["start"]:
                # Swap current label
                self.current_label = 1 - self.current_label
                # Update current singing line on the "current label"
                self.labels[self.current_label].setText(seg["text"])

                # Preload next line on the other label
                next_next_index = self.next_index + 1
                if next_next_index < len(self.lyrics_segments):
                    self.labels[1 - self.current_label].setText(
                        self.lyrics_segments[next_next_index]["text"]
                    )
                else:
                    # No more lines, clear the other label
                    self.labels[1 - self.current_label].setText("")

                self.current_index = self.next_index
                self.next_index += 1

        # Stop when playback finishes
        import pygame
        if not pygame.mixer.Channel(0).get_busy() and self.player.get_state() == vlc.State.Ended:
            self.timer.stop()
            self.playing = False
            for lbl in self.labels:
                lbl.setText("")
            print("✅ Playback finished.")
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
        """Stop current playback."""
        import pygame
        pygame.mixer.stop()
        self.playing = False
        self.timer.stop()
        if self.player.is_playing():
            self.player.stop()
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
