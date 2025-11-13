# main.py

from searcher.youtube_search import YouTubeSearcher
from downloader.yt_downloader import YouTubeDownloader
from processor.vocal_remover import VocalRemover
from processor.lyrics_manager import LyricsManager
from processor.karaoke_player import KaraokePlayer

def main():
    print("🎤 Welcome to KaraokeApp (Phase 1)")
    print("Type the song name or artist to search:")

    query = input("🔍 Search: ").strip()
    if not query:
        print("❌ Please enter a search keyword.")
        return

    # Initialize modules
    searcher = YouTubeSearcher()
    downloader = YouTubeDownloader()

    # Search YouTube Music
    print(f"\nSearching for '{query}' ...\n")
    results = searcher.search(query, max_results=5)

    if not results:
        print("❌ No results found.")
        return

    # Display results
    print("🎵 Top results:")
    for idx, r in enumerate(results, 1):
        print(f"{idx}. {r['title']} - {r['artist']} ({r['duration']})")

    # Ask user to pick one
    choice = input("\nEnter the number of the song to download: ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(results):
        print("❌ Invalid choice.")
        return

    selected = results[int(choice) - 1]
    print(f"\n⬇️ Downloading '{selected['title']}' by {selected['artist']} ...")
    file_path = downloader.download_audio(selected['url'])

    if file_path:
        print(f"✅ Download complete! File saved at:\n{file_path}")
    else:
        print("❌ Download failed.")

    remover = VocalRemover()
    instrumental_path, vocals_path = remover.remove_vocals(file_path)


    if instrumental_path:
        print(f"🎤 Your karaoke track is ready: {instrumental_path}")

    # After downloading audio & removing vocals
    lyrics_manager = LyricsManager()
    segments = lyrics_manager.transcribe(vocals_path)
    lrc_path = f"{vocals_path}.lrc"
    lyrics_manager.save_lrc(segments, lrc_path)

    # Stream YouTube video + instrumental + lyrics
    player = KaraokePlayer(instrumental_path, segments, selected['url'])
    player.start()


if __name__ == "__main__":
    main()
