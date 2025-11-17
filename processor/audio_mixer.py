# audio_mixer.py
import os
import threading
import numpy as np
from pydub import AudioSegment
import pygame
import sounddevice as sd


class AudioMixer:
    def __init__(self):
        """Initialize pygame mixer and internal state."""
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
        pygame.mixer.set_num_channels(4)  # 0=instrumental, 1=vocals, 2=mic
        self.instrumental = None
        self.vocals = None
        self.vocal_enabled = True

        self.paused = False    # ← NEW

    # -----------------------------
    #   Load audio files
    # -----------------------------
    def load_instrumental(self, path: str):
        if not path or not os.path.exists(path):
            self.instrumental = None
            return
        audio = AudioSegment.from_file(path).set_channels(2).set_frame_rate(44100)
        audio.export("temp_instrumental.wav", format="wav")
        self.instrumental = pygame.mixer.Sound("temp_instrumental.wav")

    def load_vocals(self, path: str):
        if not path or not os.path.exists(path):
            self.vocals = None
            return
        audio = AudioSegment.from_file(path).set_channels(2).set_frame_rate(44100)
        audio.export("temp_vocal.wav", format="wav")
        self.vocals = pygame.mixer.Sound("temp_vocal.wav")

    # -----------------------------
    #   Playback control
    # -----------------------------
    def play(self):
        if self.instrumental:
            pygame.mixer.Channel(0).play(self.instrumental)
        if self.vocals:
            pygame.mixer.Channel(1).play(self.vocals)
            pygame.mixer.Channel(1).set_volume(1.0 if self.vocal_enabled else 0.0)

    def pause(self):
        pygame.mixer.pause()
        self.paused = True

    def resume(self):
        pygame.mixer.unpause()
        self.paused = False

    def stop(self):
        pygame.mixer.stop()

    def set_vocal_volume(self, volume: float):
        self.vocal_enabled = volume > 0
        if self.vocals:
            pygame.mixer.Channel(1).set_volume(volume)

    def is_playing(self):
        # Playing if it's not paused AND channel is active
        return pygame.mixer.Channel(0).get_busy() or self.paused

    def get_position(self):
        """Return current playback time of instrumental in seconds."""
        channel = pygame.mixer.Channel(0)
        if self.instrumental and channel.get_busy():
            # pygame doesn't give exact time, so track manually with a timer
            return getattr(self, "_position", 0.0)
        return 0.0

    def get_length(self):
        """Return total length of instrumental in seconds."""
        if self.instrumental:
            return self.instrumental.get_length()
        return 0.0

    def seek(self, seconds):
        """Jump to a certain position in the instrumental AND vocal tracks."""
        # --- Stop playback ---
        pygame.mixer.Channel(0).stop()
        pygame.mixer.Channel(1).stop()

        # --- Reload instrumental ---
        if self.instrumental:
            inst_audio = AudioSegment.from_file("temp_instrumental.wav")
            inst_audio = inst_audio[seconds*1000:]  # milliseconds
            inst_audio.export("temp_instrumental_seek.wav", format="wav")
            self.instrumental = pygame.mixer.Sound("temp_instrumental_seek.wav")

        # --- Reload vocals ---
        if self.vocals:
            voc_audio = AudioSegment.from_file("temp_vocal.wav")
            voc_audio = voc_audio[seconds*1000:]
            voc_audio.export("temp_vocal_seek.wav", format="wav")
            self.vocals = pygame.mixer.Sound("temp_vocal_seek.wav")

        # --- Resume playback ---
        self.play()

if __name__ == "__main__":
    mixer = AudioMixer()

    # Select headphone mic as input
    mic_keywords = ["headset", "headphone", "mic", "jack", "line in"]
    input_index = None
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and any(k in dev["name"].lower() for k in mic_keywords):
            input_index = idx
            print(f"🎤 Selected input device: {dev['name']} (index={idx})")
            break
    if input_index is None:
        input_index = sd.default.device[0]

    # Use default output device
    output_index = sd.default.device[1]
    print(f"🔊 Using output device index: {output_index}")

    mixer.start_live_input(input_device_index=input_index, output_device_index=output_index)

    try:
        import time
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        mixer.stop_mic()
