# searcher/youtube_search.py
from ytmusicapi import YTMusic

class YouTubeSearcher:
    def __init__(self):
        # initialize YTMusic (can use empty headers for basic search)
        self.ytmusic = YTMusic()

    def search(self, query, max_results=5):
        """
        Search YouTube for a query and return a list of dicts:
        {title, videoId, artists, duration}
        """
        results = self.ytmusic.search(query, filter='songs')  # songs only
        output = []
        for r in results[:max_results]:
            info = {
                'title': r.get('title'),
                'videoId': r.get('videoId'),
                'artist': r.get('artists', [{}])[0].get('name', ''),
                'duration': r.get('duration'),
                'url': f"https://www.youtube.com/watch?v={r.get('videoId')}"
            }
            output.append(info)
        return output

# Test code
if __name__ == "__main__":
    ys = YouTubeSearcher()
    query = "隱形遊樂場"
    results = ys.search(query, max_results=5)
    for r in results:
        print(r)
