import threading
import tkinter as tk
from tkinter import ttk, messagebox
from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer  # ✅ Use your full karaoke player with video

class KaraokeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎤 KaraokeApp")
        self.root.geometry("900x600")

        # Core modules
        self.searcher = YouTubeSearcher()
        self.downloader = YouTubeDownloader()
        self.remover = VocalRemover()
        self.lyrics_manager = LyricsManager()

        # States
        self.results = []
        self.current_song = None
        self.player = None

        self.setup_ui()

    def setup_ui(self):
        # 🔍 Search area
        self.query_entry = ttk.Entry(self.root, width=50)
        self.query_entry.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.search_btn = ttk.Button(self.root, text="Search", command=self.search_songs)
        self.search_btn.grid(row=0, column=1, padx=10, pady=10)

        # Results list
        self.results_box = tk.Listbox(self.root, height=10, width=80)
        self.results_box.grid(row=1, column=0, columnspan=2, padx=10, pady=10)

        # Prepare button
        self.prepare_btn = ttk.Button(self.root, text="Prepare Karaoke", command=self.prepare_karaoke)
        self.prepare_btn.grid(row=2, column=0, columnspan=2, pady=10)

        # Status label
        self.status_label = ttk.Label(self.root, text="Status: Idle")
        self.status_label.grid(row=3, column=0, columnspan=2, pady=5)

        # Control buttons
        controls = ttk.Frame(self.root)
        controls.grid(row=4, column=0, columnspan=2, pady=15)
        self.play_btn = ttk.Button(controls, text="▶️ Play", command=self.play_song)
        self.play_btn.grid(row=0, column=0, padx=5)
        self.stop_btn = ttk.Button(controls, text="⏹ Stop", command=self.stop_song)
        self.stop_btn.grid(row=0, column=1, padx=5)

        # Queue/lyrics preview
        self.lyrics_text = tk.Text(self.root, wrap="word", height=15, width=90)
        self.lyrics_text.grid(row=5, column=0, columnspan=2, padx=10, pady=10)

    def update_status(self, text):
        self.status_label.config(text=f"Status: {text}")
        self.root.update_idletasks()

    def search_songs(self):
        query = self.query_entry.get().strip()
        if not query:
            messagebox.showerror("Error", "Please enter a song name.")
            return

        self.update_status(f"Searching for '{query}'...")
        self.results = self.searcher.search(query, max_results=5)

        self.results_box.delete(0, tk.END)
        for r in self.results:
            self.results_box.insert(tk.END, f"{r['title']} - {r['artist']} ({r['duration']})")

        self.update_status("Search complete ✅")

    def prepare_karaoke(self):
        selection = self.results_box.curselection()
        if not selection:
            messagebox.showerror("Error", "Select a song first.")
            return

        selected = self.results[selection[0]]

        threading.Thread(target=self._prepare_thread, args=(selected,), daemon=True).start()

    def _prepare_thread(self, selected):
        self.update_status(f"Downloading {selected['title']}...")
        file_path = self.downloader.download_audio(selected['url'])

        if not file_path:
            self.update_status("Download failed ❌")
            return

        self.update_status("Removing vocals (Demucs)...")
        instrumental_path, vocals_path = self.remover.remove_vocals(file_path)

        self.update_status("Transcribing lyrics...")
        segments = self.lyrics_manager.transcribe(vocals_path)
        lrc_path = f"{vocals_path}.lrc"
        self.lyrics_manager.save_lrc(segments, lrc_path)

        self.current_song = {
            "title": selected["title"],
            "url": selected["url"],
            "instrumental": instrumental_path,
            "segments": segments,
        }

        self.display_lyrics(segments)
        self.update_status("Karaoke ready ✅")

    def display_lyrics(self, segments):
        self.lyrics_text.delete("1.0", tk.END)
        for seg in segments:
            self.lyrics_text.insert(tk.END, f"{seg['text']}\n")

    def play_song(self):
        if not self.current_song:
            messagebox.showinfo("Info", "Please prepare a karaoke first.")
            return

        # 💡 Use your full video+lyrics KaraokePlayer
        self.update_status("Launching Karaoke Player...")
        threading.Thread(
            target=self._launch_karaoke_window,
            args=(self.current_song,),
            daemon=True
        ).start()

    def _launch_karaoke_window(self, song):
        # This opens the video+lyrics player window (Tkinter + OpenCV)
        player = KaraokePlayer(
            audio_path=song["instrumental"],
            lyrics_segments=song["segments"],
            video_url=song["url"]
        )
        player.start()  # this runs its own Tkinter mainloop

    def stop_song(self):
        messagebox.showinfo("Info", "Close the Karaoke window to stop playback.")


if __name__ == "__main__":
    root = tk.Tk()
    app = KaraokeApp(root)
    root.mainloop()
