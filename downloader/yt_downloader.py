# downloader/yt_downloader.py

import os
import yt_dlp
from utils.filename_safety import safe_name_long   # you already have this

class YouTubeDownloader:
    def download_audio(self, song_dir, url: str) -> str:
        """
        Downloads the best audio from YouTube with a fully sanitized filename.
        """
        print(f"🔍 Downloading audio from: {url}")

        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                raw_title = info.get("title", "audio")
        except Exception:
            raw_title = "audio"

        safe_title = safe_name_long(raw_title)

        outtmpl = os.path.join(song_dir, f"{safe_title}.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'noplaylist': True,
            'ignoreerrors': True,

            # 🔑 CRITICAL
            'user_agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/121.0.0.0 Safari/537.36'
            ),
            'referer': 'https://www.youtube.com/',
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                print(f"✅ Downloaded (safe): {filename}")
                return filename
        except Exception as e:
            print(f"❌ Download error: {e}")
            return None



if __name__ == "__main__":
    # Example test usage
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    downloader = YouTubeDownloader()
    audio_path = downloader.download_audio(test_url)
    print("Saved file:", audio_path)
