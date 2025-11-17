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

        # Microphone stream
        self.mic_stream = None
        self.mic_enabled = False

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
        self.stop_mic()

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

    def get_input_devices(self):
        import pyaudio
        p = pyaudio.PyAudio()

        devices = {}
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices[i] = info["name"]

        p.terminate()
        return devices

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


    def play_input_device(self, input_device_index=None, output_device_index=None):
        """Ultra low-latency mic → speaker playback with separate devices."""
        self.stop_mic()
        self.mic_enabled = True

        if input_device_index is None:
            input_device_index = sd.default.device[0]
        if output_device_index is None:
            output_device_index = sd.default.device[1]

        input_info = sd.query_devices(input_device_index)
        output_info = sd.query_devices(output_device_index)

        samplerate = int(input_info["default_samplerate"])
        input_channels = min(input_info["max_input_channels"], 1)  # mono mic
        output_channels = min(output_info["max_output_channels"], 2)  # stereo output

        print(f"🎤 Input: {input_info['name']} ({samplerate} Hz, {input_channels} ch)")
        print(f"🔊 Output: {output_info['name']} ({samplerate} Hz, {output_channels} ch)")

        def callback(indata, outdata, frames, time, status):
            if not self.mic_enabled:
                outdata.fill(0)
                return
            if status:
                print("⚠️ Stream status:", status)
            # Copy mono input to stereo output
            if input_channels == 1 and output_channels == 2:
                outdata[:, 0] = indata[:, 0]
                outdata[:, 1] = indata[:, 0]
            else:
                outdata[:] = indata

        self.mic_stream = sd.Stream(
            samplerate=samplerate,
            blocksize=128,
            latency='low',
            dtype='float32',
            channels=(input_channels, output_channels),
            device=(input_device_index, output_device_index),
            callback=callback
        )
        self.mic_stream.start()
        print("▶ Ultra low-latency mic playback started.")

    def stop_input_device(self):
        self._loopback_running = False

    def start_live_input(self, input_device_index=None, output_device_index=None):
        """Ultra low-latency mic → speaker playback with separate devices."""
        self.stop_mic()
        self.mic_enabled = True

        if input_device_index is None:
            input_device_index = sd.default.device[0]
        if output_device_index is None:
            output_device_index = sd.default.device[1]

        input_info = sd.query_devices(input_device_index)
        output_info = sd.query_devices(output_device_index)

        samplerate = int(input_info["default_samplerate"])
        input_channels = min(input_info["max_input_channels"], 1)  # mono mic
        output_channels = min(output_info["max_output_channels"], 2)  # stereo output

        print(f"🎤 Input: {input_info['name']} ({samplerate} Hz, {input_channels} ch)")
        print(f"🔊 Output: {output_info['name']} ({samplerate} Hz, {output_channels} ch)")

        def callback(indata, outdata, frames, time, status):
            if not self.mic_enabled:
                outdata.fill(0)
                return
            if status:
                print("⚠️ Stream status:", status)
            # Copy mono input to stereo output
            if input_channels == 1 and output_channels == 2:
                outdata[:, 0] = indata[:, 0]
                outdata[:, 1] = indata[:, 0]
            else:
                outdata[:] = indata

        self.mic_stream = sd.Stream(
            samplerate=samplerate,
            blocksize=128,
            latency='low',
            dtype='float32',
            channels=(input_channels, output_channels),
            device=(input_device_index, output_device_index),
            callback=callback
        )
        self.mic_stream.start()
        print("▶ Ultra low-latency mic playback started.")

    def stop_mic(self):
        self.mic_enabled = False
        if self.mic_stream:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except:
                pass
            self.mic_stream = None
        pygame.mixer.Channel(2).stop()
        print("🛑 Mic playback stopped.")

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
