# processor/lyrics_handler.py

import os
import re
import requests
from bs4 import BeautifulSoup

# aeneas imports (for timed lyrics)
from aeneas.executetask import ExecuteTask
from aeneas.task import Task

def safe_filename(name: str) -> str:
    """Convert string to ASCII-safe string for file paths."""
    return "".join(c if c.isalnum() else "_" for c in name)


def search_mojim_lyrics(song_name: str, artist_name: str = "") -> str:
    """
    Search and scrape lyrics from mojim.com for Cantonese/Taiwanese songs.
    Returns plain text lyrics.
    """
    base_search = "https://mojim.com/cgi-bin/search.cgi"
    params = {"key": song_name}
    response = requests.get(base_search, params=params)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    # Find first result
    results = soup.select("dd > a")  # Links to song pages
    song_url = None
    for r in results:
        title = r.get_text()
        if artist_name in title or True:  # fallback if artist not specified
            song_url = "https://mojim.com" + r["href"]
            break
    if not song_url:
        return None

    # Scrape lyrics from song page
    page = requests.get(song_url)
    page.encoding = "utf-8"
    page_soup = BeautifulSoup(page.text, "html.parser")
    lyrics_div = page_soup.find("dd", {"id": "fsZx3"})  # lyrics container
    if not lyrics_div:
        return None

    lyrics_text = lyrics_div.get_text(separator="\n")
    lyrics_text = re.sub(r"\[.*?\]", "", lyrics_text)  # remove tags like [Chorus]
    lyrics_text = re.sub(r"\n+", "\n", lyrics_text).strip()
    return lyrics_text


def save_lyrics(lyrics: str, output_folder: str, song_name: str) -> str:
    """
    Save plain lyrics to a .txt file.
    Returns the saved path.
    """
    os.makedirs(output_folder, exist_ok=True)
    filename = safe_filename(song_name) + ".txt"
    path = os.path.join(output_folder, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(lyrics)
    return path


def generate_lrc(audio_path: str, lyrics_text_path: str, output_folder: str, song_name: str) -> str:
    """
    Generate timed .lrc lyrics using aeneas.
    Requires aeneas installed: pip install aeneas
    """
    os.makedirs(output_folder, exist_ok=True)
    lrc_filename = safe_filename(song_name) + ".lrc"
    lrc_path = os.path.join(output_folder, lrc_filename)

    # Configure aeneas task
    task_config = "task_language=zh|is_text_type=plain|os_task_file_format=lrc"
    task = Task(config_string=task_config)
    task.audio_file_path_absolute = os.path.abspath(audio_path)
    task.text_file_path_absolute = os.path.abspath(lyrics_text_path)
    task.output_file_path_absolute = os.path.abspath(lrc_path)

    # Execute
    ExecuteTask(task).execute()
    task.output_sync_map_file()
    return lrc_path


def process_lyrics(song_name: str, artist_name: str, audio_path: str, output_folder: str = "lyrics"):
    """
    Full pipeline:
    1. Search lyrics
    2. Save plain text
    3. Generate timed .lrc using aeneas
    Returns paths to plain lyrics and .lrc file.
    """
    lyrics = search_mojim_lyrics(song_name, artist_name)
    if not lyrics:
        print("❌ Lyrics not found.")
        return None, None

    txt_path = save_lyrics(lyrics, output_folder, song_name)
    try:
        lrc_path = generate_lrc(audio_path, txt_path, output_folder, song_name)
        print(f"✅ Generated timed lyrics: {lrc_path}")
    except Exception as e:
        print(f"⚠️ Failed to generate timed lyrics: {e}")
        lrc_path = None

    return txt_path, lrc_path
