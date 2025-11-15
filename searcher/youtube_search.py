# searcher/youtube_search.py
from yt_dlp import YoutubeDL
import threading

class YouTubeSearcher:
    def __init__(self):
        pass

    def search(self, query, max_results=5):
        """
        Fast YouTube search returning a list of dicts:
        {title, videoId, artist, duration, url}
        """
        results = []

        # Step 1: Fast flat search (extract only basic info)
        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',  # Only basic info, no full metadata
            'skip_download': True
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = info.get('entries', [])

        # Step 2: Fetch metadata for each entry (lightweight)
        def fetch_metadata(entry, output_list):
            with YoutubeDL({'quiet': True}) as ydl:
                try:
                    full_info = ydl.extract_info(f"https://www.youtube.com/watch?v={entry['id']}", download=False)
                    artist = full_info.get('artist') or full_info.get('uploader') or ""
                    duration = full_info.get('duration')
                except:
                    artist = ""
                    duration = None
                output_list.append({
                    'title': entry.get('title'),
                    'videoId': entry.get('id'),
                    'artist': artist,
                    'duration': duration,
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                })

        threads = []
        for e in entries:
            t = threading.Thread(target=fetch_metadata, args=(e, results))
            t.start()
            threads.append(t)

        # Wait for all threads to finish
        for t in threads:
            t.join()

        # Sort results to preserve original order
        results.sort(key=lambda x: entries.index(next(e for e in entries if e['id'] == x['videoId'])))
        return results
