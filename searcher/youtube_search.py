# searcher/youtube_search.py
from yt_dlp import YoutubeDL

class YouTubeSearcher:
    def __init__(self):
        pass  # no initialization needed

    def search(self, query, max_results=5):
        """
        Search YouTube for a query and return a list of dicts:
        {title, videoId, artist, duration, url}
        """
        ydl_opts = {'quiet': True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            results = []
            for entry in info['entries']:
                # Fallback for artist: use uploader if no music metadata
                artist = entry.get('artist') or entry.get('uploader') or ""
                results.append({
                    'title': entry.get('title'),
                    'videoId': entry.get('id'),
                    'artist': artist,
                    'duration': entry.get('duration'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
            return results

# Test code
if __name__ == "__main__":
    ys = YouTubeSearcher()
    query = "隱形遊樂場"
    results = ys.search(query, max_results=5)
    for r in results:
        print(r)
