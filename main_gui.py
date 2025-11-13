# main_gui.py

import tkinter as tk
from tkinter import ttk, messagebox
from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer
from cache.cache_manager import CacheManager
import threading
import os

class KaraokeApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Karaoke App")
        self.root.geometry("900x600")

        self.searcher = YouTubeSearcher()
        self.downloader = YouTubeDownloader()
        self.cache = CacheManager()
        self.player = None

        self.results = []
        self.segments = []
        self.current_song = None

        self._setup_ui()

    def _setup_ui(self):
        # Top frame for search
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(top_frame, text="Search Song/Artist:").pack(side="left")
        self.search_entry = tk.Entry(top_frame, width=40)
        self.search_entry.pack(side="left", padx=5)
        tk.Button(top_frame, text="Search", command=self.search).pack(side="left")

        # Middle frame for results and cache
        middle_frame = tk.Frame(self.root)
        middle_frame.pack(fill="both", expand=True, padx=10, pady=5)

        tk.Label(middle_frame, text="Search Results:").pack(anchor="w")
        self.results_list = tk.Listbox(middle_frame, height=10)
        self.results_list.pack(fill="x", pady=2)
        self.results_list.bind("<<ListboxSelect>>", self.select_song)

        tk.Label(middle_frame, text="Cached Songs:").pack(anchor="w", pady=(10,0))
        self.cache_list = tk.Listbox(middle_frame, height=5)
        self.cache_list.pack(fill="x", pady=2)
        self.cache_list.bind("<<ListboxSelect>>", self.select_cached_song)
        self.refresh_cache_list()

        # Bottom frame for controls
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(bottom_frame, text="Play", command=self.play_song).pack(side="left", padx=5)
        tk.Button(bottom_frame, text="Pause", command=self.pause_song).pack(side="left", padx=5)
        tk.Button(bottom_frame, text="Stop", command=self.stop_song).pack(side="left", padx=5)

    def refresh_cache_list(self):
        self.cache_list.delete(0, tk.END)
        for folder in self.cache.BASE_DIR.iterdir():
            if folder.is_dir():
                meta_path = folder / "meta.json"
                if meta_path.exists():
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        self.cache_list.insert(tk.END, f"{meta['artist']} - {meta['title']}")

    def search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a search keyword.")
            return

        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        self.results_list.delete(0, tk.END)
        self.results = self.searcher.search(query, max_results=5)
        for r in self.results:
            self.results_list.insert(tk.END, f"{r['artist']} - {r['title']} ({r['duration']})")

    def select_song(self, event):
        idx = self.results_list.curselection()
        if idx:
            self.current_song = self.results[idx[0]]

    def select_cached_song(self, event):
        idx = self.cache_list.curselection()
        if idx:
            folder_name = list(self.cache.BASE_DIR.iterdir())[idx[0]]
            cached = self.cache.check_existing(folder_name.stem.split("_",1)[1], folder_name.stem.split("_",1)[0])
            if cached:
                self.current_song = {"title": folder_name.stem.split("_",1)[1],
                                     "artist": folder_name.stem.split("_",1)[0],
                                     "url": cached['url'],
                                     "cached": cached}

    def play_song(self):
        if not self.current_song:
            messagebox.showwarning("Warning", "No song selected.")
            return

        # If cached, use cached files
        if "cached" in self.current_song:
            instrumental_path = self.current_song["cached"]["instrumental"]
            lrc_path = self.current_song["cached"]["lyrics"]
            segments = []

            with open(lrc_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("["):
                        time_part, text = line.strip().split("]", 1)
                        min_sec = time_part[1:].split(":")
                        start = float(min_sec[0]) * 60 + float(min_sec[1])
                        segments.append({"start": start, "end": start + 5.0, "text": text})
        else:
            # Download and process song
            file_path = self.downloader.download_audio(self.current_song["url"])
            remover = VocalRemover()
            instrumental_path, vocals_path = remover.remove_vocals(file_path,
                                                                  self.current_song["title"],
                                                                  self.current_song["artist"])
            lyrics_manager = LyricsManager()
            segments = lyrics_manager.transcribe(vocals_path, self.current_song["title"], self.current_song["artist"])
            lrc_path = f"{vocals_path}.lrc"
            lyrics_manager.save_lrc(segments, lrc_path)
            self.cache.save_meta(self.current_song["title"], self.current_song["artist"], self.current_song["url"])

        # Start KaraokePlayer
        if self.player:
            self.player.playing = False  # stop previous
        self.player = KaraokePlayer(instrumental_path, segments, self.current_song.get("url"))
        threading.Thread(target=self.player.start, daemon=True).start()

    def pause_song(self):
        if self.player:
            import pygame
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()

    def stop_song(self):
        if self.player:
            self.player.playing = False
            import pygame
            pygame.mixer.music.stop()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    import json
    app = KaraokeApp()
    app.run()
