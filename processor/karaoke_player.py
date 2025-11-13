import os
import time
import tkinter as tk
from yt_dlp import YoutubeDL
from pydub import AudioSegment
import vlc
import pygame


class KaraokePlayer:
    def __init__(self, instrumental_path, lyrics_segments, vocal_path=None, video_path=None, video_url=None):
        self.instrumental_path = instrumental_path
        self.vocal_path = vocal_path
        self.lyrics_segments = lyrics_segments
        self.video_path = video_path
        self.video_url = video_url

        self.window = None
        self.playing = False
        self.vocal_enabled = False  # toggle flag

        # VLC player for video
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        self._prepare_audio_files()

    def _prepare_audio_files(self):
        """Ensure WAV files are in playable PCM format"""
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
        """Download YouTube video if URL provided"""
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

    def _setup_tkinter(self):
        """Create Tkinter window for video + lyrics + button"""
        self.window = tk.Tk()
        self.window.title("Karaoke Player")
        self.window.geometry("800x600")

        self.video_frame = tk.Frame(self.window, bg="black")
        self.video_frame.pack(expand=True, fill="both")

        self.lyrics_label = tk.Label(
            self.window, text="", font=("Arial", 24), bg="black", fg="white"
        )
        self.lyrics_label.pack(pady=10)

        self.toggle_button = tk.Button(
            self.window,
            text="Enable Vocal",
            font=("Arial", 14),
            command=self._toggle_vocal
        )
        self.toggle_button.pack(pady=10)

    def _toggle_vocal(self):
        """Toggle vocal playback"""
        if not self.vocal_pcm:
            print("⚠️ No vocal track available.")
            return

        self.vocal_enabled = not self.vocal_enabled
        self.toggle_button.config(
            text="Disable Vocal" if self.vocal_enabled else "Enable Vocal"
        )

        if self.vocal_enabled:
            # start or unmute vocal
            pygame.mixer.Channel(1).set_volume(1.0)
        else:
            # mute vocal
            pygame.mixer.Channel(1).set_volume(0.0)

    def _play_media(self):
        """Play video (muted) and audio via pygame"""
        # Setup VLC for video
        if self.video_path and os.path.exists(self.video_path):
            media = self.instance.media_new(self.video_path)
            self.player.set_media(media)
            self.window.update_idletasks()
            handle = self.video_frame.winfo_id()
            if os.name == "nt":
                self.player.set_hwnd(handle)
            else:
                try:
                    self.player.set_xwindow(handle)
                except Exception:
                    try:
                        self.player.set_nsobject(handle)
                    except Exception:
                        pass

            self.player.audio_set_mute(True)
            self.player.play()
            start_wait = time.time()
            while not self.player.is_playing() and (time.time() - start_wait) < 1.0:
                time.sleep(0.01)

        # Init pygame mixer (2 channels: instrumental + vocal)
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
        pygame.mixer.set_num_channels(2)

        # Load instrumental on Channel 0
        instrumental_sound = pygame.mixer.Sound(self.instrumental_pcm)
        pygame.mixer.Channel(0).play(instrumental_sound)

        # Load vocal on Channel 1 (muted initially)
        if self.vocal_pcm:
            vocal_sound = pygame.mixer.Sound(self.vocal_pcm)
            pygame.mixer.Channel(1).play(vocal_sound)
            pygame.mixer.Channel(1).set_volume(0.0)

        self.start_time = time.time()
        self.playing = True

    def _update_lyrics_sync(self):
        """Sync lyrics with instrumental playback"""
        if not self.playing:
            return

        elapsed = time.time() - self.start_time
        current_text = ""
        for seg in self.lyrics_segments:
            if seg["start"] <= elapsed < seg["end"]:
                current_text = seg["text"]
                break
        self.lyrics_label.config(text=current_text)

        # Check if instrumental still playing
        if pygame.mixer.Channel(0).get_busy():
            self.window.after(50, self._update_lyrics_sync)
        else:
            self.lyrics_label.config(text="")
            self.playing = False
            print("✅ Playback finished.")

    def start(self):
        """Start karaoke"""
        self._setup_tkinter()
        if self.video_url:
            self._download_video()
        self._play_media()
        self._update_lyrics_sync()
        self.window.mainloop()


if __name__ == "__main__":
    test_url = "https://www.youtube.com/watch?v=UwuAPyOImoI"

    song_dir = "./karaoke_data/BIGBANG_TAEYANG - 눈,코,입 (EYES, NOSE, LIPS) M_V"
    instrumental = f"{song_dir}/instrumental.wav"
    vocal = f"{song_dir}/vocals.wav"
    lrc_path = f"{song_dir}/vocals.wav.lrc"

    print("Audio exists:", os.path.exists(instrumental))
    print("Vocal exists:", os.path.exists(vocal))
    print("Lyrics exists:", os.path.exists(lrc_path))

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

    print("🎬 Starting KaraokePlayer test...")
    player = KaraokePlayer(instrumental, segments, vocal_path=vocal, video_url=test_url)
    player.start()
