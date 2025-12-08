from pathlib import Path
from datetime import datetime
import threading

_lock = threading.Lock()
_log_path = Path.cwd() / "karaoke_debug.log"

def write_debug(msg: str):
    """Append a timestamped debug message to the debug log file."""
    try:
        line = f"[{datetime.now().isoformat()}] {msg}\n"
        with _lock:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        # Best-effort logging; do not raise
        pass

def set_log_path(path: Path):
    global _log_path
    _log_path = Path(path)
