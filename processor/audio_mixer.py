# audio_mixer.py
import os
from pydub import AudioSegment
import pygame

class AudioMixer:
    def __init__(self):
        """Initialize pygame mixer and internal state."""
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
        pygame.mixer.set_num_channels(2)  # 0 = instrumental, 1 = vocals
        self.instrumental = None
        self.vocals = None
        self.vocal_enabled = True

    def load_instrumental(self, path: str):
        """Load instrumental audio and convert to WAV if needed."""
        if not path or not os.path.exists(path):
            self.instrumental = None
            return
        audio = AudioSegment.from_file(path).set_channels(2).set_frame_rate(44100)
        audio.export("temp_instrumental.wav", format="wav")
        self.instrumental = pygame.mixer.Sound("temp_instrumental.wav")

    def load_vocals(self, path: str):
        """Load vocal audio and convert to WAV if needed."""
        if not path or not os.path.exists(path):
            self.vocals = None
            return
        audio = AudioSegment.from_file(path).set_channels(2).set_frame_rate(44100)
        audio.export("temp_vocal.wav", format="wav")
        self.vocals = pygame.mixer.Sound("temp_vocal.wav")

    def play(self):
        """Play loaded tracks."""
        if self.instrumental:
            pygame.mixer.Channel(0).play(self.instrumental)
        if self.vocals:
            pygame.mixer.Channel(1).play(self.vocals)
            # Apply current vocal volume
            pygame.mixer.Channel(1).set_volume(1.0 if self.vocal_enabled else 0.0)

    def pause(self):
        """Pause all tracks."""
        pygame.mixer.pause()

    def resume(self):
        """Resume all tracks."""
        pygame.mixer.unpause()

    def stop(self):
        """Stop all tracks immediately."""
        pygame.mixer.stop()

    def set_vocal_volume(self, volume: float):
        """Set vocal volume (0.0 = muted, 1.0 = full)."""
        self.vocal_enabled = volume > 0
        if self.vocals:
            pygame.mixer.Channel(1).set_volume(volume)

    def is_playing(self):
        """Return True if instrumental track is still playing."""
        return pygame.mixer.Channel(0).get_busy()
