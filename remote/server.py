from flask import Flask, request, jsonify
from flask_socketio import SocketIO
import numpy as np
import sounddevice as sd
import base64
import threading
from queue import Queue

class RemoteServer:
    def __init__(self, app_ref):
        self.app_ref = app_ref  # reference to KaraokeAppQt
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")

        # Track connected mics
        self.connected_mics = set()

        # Queue for incoming audio chunks
        self.audio_queue = Queue()

        # Sounddevice stream (continuous playback)
        self.stream = sd.OutputStream(samplerate=44100, channels=1, dtype='float32',
                                      callback=self._audio_callback)
        self.stream.start()

        # --- REST API endpoints ---
        @self.app.route("/api/play", methods=["POST"])
        def play():
            self.app_ref.play_song()
            return jsonify({"status": "playing"})

        @self.app.route("/api/pause", methods=["POST"])
        def pause():
            self.app_ref.pause_song()
            return jsonify({"status": "paused"})

        @self.app.route("/api/skip", methods=["POST"])
        def skip():
            self.app_ref.skip_song()
            return jsonify({"status": "skipped"})

        @self.app.route("/api/queue", methods=["POST"])
        def queue_song():
            data = request.json
            self.app_ref.current_selected = data
            self.app_ref.queue_song()
            return jsonify({"status": "queued"})

        @self.app.route("/api/state", methods=["GET"])
        def state():
            return jsonify({
                "queue": self.app_ref.queue,
                "now_playing": getattr(self.app_ref.player_window, "current_title", None)
            })

        # --- Remote page ---
        @self.app.route("/remote")
        def remote_page():
            return self.app.send_static_file("index.html")

        # --- Socket.IO events for mic streaming ---
        @self.socketio.on("connect")
        def handle_connect():
            self.connected_mics.add(request.sid)
            print(f"Mic connected. Total: {len(self.connected_mics)}")
            if hasattr(self.app_ref, "update_mic_count"):
                self.app_ref.update_mic_count(len(self.connected_mics))

        @self.socketio.on("disconnect")
        def handle_disconnect():
            self.connected_mics.discard(request.sid)
            print(f"Mic disconnected. Total: {len(self.connected_mics)}")
            if hasattr(self.app_ref, "update_mic_count"):
                self.app_ref.update_mic_count(len(self.connected_mics))

        @self.socketio.on("audio_chunk")
        def handle_audio(data):
            audio_bytes = base64.b64decode(data.split(",")[1])
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            self.audio_queue.put(audio_array)

    def _audio_callback(self, outdata, frames, time, status):
        if status:
            print("Audio status:", status)
        try:
            chunk = self.audio_queue.get_nowait()
            if len(chunk) < len(outdata):
                outdata[:len(chunk), 0] = chunk
                outdata[len(chunk):, 0] = 0
            else:
                outdata[:, 0] = chunk[:len(outdata)]
        except:
            outdata.fill(0)

    def start(self):
        """
        Start Flask + Socket.IO server in a background thread.
        """
        threading.Thread(
            target=lambda: self.socketio.run(self.app, host="0.0.0.0", port=5005),
            daemon=True
        ).start()
