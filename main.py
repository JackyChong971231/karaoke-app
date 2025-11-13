# main.py

from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer
from cache.cache_manager import CacheManager

def main():
    print("🎤 Welcome to KaraokeApp (Phase 1)")

    query = input("🔍 Search: ").strip()
    if not query:
        print("❌ Please enter a search keyword.")
        return

    searcher = YouTubeSearcher()
    downloader = YouTubeDownloader()
    cache = CacheManager()

    results = searcher.search(query, max_results=5)
    if not results:
        print("❌ No results found.")
        return

    print("🎵 Top results:")
    for idx, r in enumerate(results, 1):
        print(f"{idx}. {r['title']} - {r['artist']} ({r['duration']})")

    choice = input("\nEnter the number of the song to download: ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(results):
        print("❌ Invalid choice.")
        return

    selected = results[int(choice) - 1]
    title, artist = selected["title"], selected["artist"]

    # Check cache first
    cached = cache.check_existing(title, artist)
    if cached:
        print(f"✅ Found cached files for '{title}'! Skipping download and processing.")
        instrumental_path = cached["instrumental"]
        vocals_path = cached["vocals"]
        lrc_path = cached["lyrics"]
    
        # Load segments from cached .lrc
        segments = []
        with open(lrc_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("["):
                    time_part, text = line.strip().split("]", 1)
                    min_sec = time_part[1:].split(":")
                    start = float(min_sec[0]) * 60 + float(min_sec[1])
                    segments.append({"start": start, "end": start + 5.0, "text": text})  # rough 5s per line
    else:
        print(f"\n⬇️ Downloading '{title}' by {artist} ...")
        file_path = downloader.download_audio(selected['url'])

        remover = VocalRemover()
        instrumental_path, vocals_path = remover.remove_vocals(file_path, title, artist)

        lyrics_manager = LyricsManager()
        segments = lyrics_manager.transcribe(vocals_path, title, artist)
        lrc_path = f"{vocals_path}.lrc"
        lyrics_manager.save_lrc(segments, lrc_path)

        cache.save_meta(title, artist, selected["url"])
        print("💾 Saved new song to cache!")

    player = KaraokePlayer(instrumental_path, segments, selected['url'])
    player.start()


if __name__ == "__main__":
    main()
