# downloader/yt_downloader.py

import os
import yt_dlp

class YouTubeDownloader:
    def __init__(self, download_dir="downloads"):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    def download_audio(self, url: str) -> str:
        """
        Downloads the best available audio from a YouTube URL.
        Returns the path to the downloaded file.
        """

        # Output path template (title + extension)
        outtmpl = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        # yt_dlp configuration
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            # Disable ffmpeg dependency (stream copy only)
            'postprocessors': [],
            'quiet': False,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
        }

        print(f"🔍 Downloading audio from: {url}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                print(f"✅ Downloaded: {filename}")
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
