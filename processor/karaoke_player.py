# processor/karaoke_player.py

import os
import time
import threading
import tkinter as tk
from yt_dlp import YoutubeDL
from pydub import AudioSegment
from PIL import Image, ImageTk
import cv2
import pygame

class KaraokePlayer:
    def __init__(self, audio_path, lyrics_segments, video_url=None):
        self.original_audio_path = audio_path
        self.audio_path = None  # Will point to PCM converted file
        self.lyrics_segments = lyrics_segments
        self.video_url = video_url
        self.window = None
        self.video_thread = None
        self.video_path = None  # downloaded video path
        self.cap = None
        self.playing = False

        # Prepare audio
        self._prepare_audio()

    def _prepare_audio(self):
        """Ensure audio is in standard 16-bit PCM WAV format"""
        if not os.path.exists(self.original_audio_path):
            print(f"❌ Audio file not found: {self.original_audio_path}")
            return
        audio = AudioSegment.from_file(self.original_audio_path)
        audio = audio.set_channels(2).set_frame_rate(44100).set_sample_width(2)
        self.audio_path = "temp_audio_pcm.wav"
        audio.export(self.audio_path, format="wav")
        print(f"✅ Converted audio: {self.audio_path}")

    def _setup_tkinter(self):
        """Create Tkinter window for video + lyrics"""
        self.window = tk.Tk()
        self.window.title("Karaoke Player")
        self.window.geometry("800x600")

        # Video area
        self.video_label = tk.Label(self.window, bg="black")
        self.video_label.pack(expand=True, fill="both")

        # Lyrics area
        self.lyrics_label = tk.Label(self.window, text="", font=("Arial", 24), bg="black", fg="white")
        self.lyrics_label.pack(pady=10)

    def _update_lyrics(self):
        """Update lyrics in sync with playback"""
        start_time = time.time()
        for segment in self.lyrics_segments:
            while (time.time() - start_time) < segment["start"]:
                time.sleep(0.05)
            self.lyrics_label.config(text=segment["text"])
        self.lyrics_label.config(text="")  # clear after song ends

    def _play_audio(self):
        """Play the instrumental track using pygame"""
        if not self.audio_path or not os.path.exists(self.audio_path):
            print(f"❌ Audio file not found: {self.audio_path}")
            return

        pygame.mixer.init()
        pygame.mixer.music.load(self.audio_path)
        pygame.mixer.music.play()
        print("🎵 Audio playback started.")

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        print("✅ Audio playback finished.")

    def _download_video(self):
        """Download video using yt_dlp"""
        if not self.video_url:
            return None
        try:
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
                "outtmpl": "temp_video.mp4",
                "quiet": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.video_url])
            self.video_path = "temp_video.mp4"
            print(f"✅ Video downloaded: {self.video_path}")
            return self.video_path
        except Exception as e:
            print(f"❌ Failed to download video: {e}")
            return None

    def _play_video(self):
        """Play downloaded video frames inside Tkinter window"""
        if not self.video_path:
            self._download_video()

        if not self.video_path or not os.path.exists(self.video_path):
            print("❌ Video file not found.")
            return

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print("❌ Failed to open video.")
            return

        print("🎥 Video playback started.")
        self.playing = True
        self._update_video_frame()

    def _update_video_frame(self):
        """Read frames from cv2 and display in Tkinter"""
        if not self.playing or not self.cap:
            return

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (800, 450))
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk)
            self.window.after(33, self._update_video_frame)  # ~30 fps
        else:
            self.cap.release()
            self.playing = False
            print("✅ Video playback finished.")

    def start(self):
        """Start the karaoke player"""
        self._setup_tkinter()

        # Start audio
        audio_thread = threading.Thread(target=self._play_audio, daemon=True)
        audio_thread.start()

        # Start video
        if self.video_url:
            video_thread = threading.Thread(target=self._play_video, daemon=True)
            video_thread.start()

        # Start lyrics
        lyrics_thread = threading.Thread(target=self._update_lyrics, daemon=True)
        lyrics_thread.start()

        self.window.mainloop()


if __name__ == "__main__":
    # Example YouTube video
    test_url = "https://www.youtube.com/watch?v=8H7I3mSxWdM"

    # Dummy lyrics
    dummy_lyrics = [
        {"start": 0.0, "end": 5.0, "text": "First line of lyrics"},
        {"start": 5.0, "end": 10.0, "text": "Second line of lyrics"},
        {"start": 10.0, "end": 15.0, "text": "Third line of lyrics"},
    ]

    # Path to dummy instrumental
    song = "俏郎君"
    dummy_audio = f"./instrumentals/{song}/htdemucs/{song}/no_vocals.wav"
    print("Audio exists:", os.path.exists(dummy_audio))

    print("🎬 Starting KaraokePlayer test...")
    player = KaraokePlayer(dummy_audio, dummy_lyrics, video_url=test_url)
    player.start()
