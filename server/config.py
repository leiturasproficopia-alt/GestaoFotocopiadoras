from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "server.db"
SESSION_COOKIE_NAME = "session_id"
SESSION_MAX_AGE = 86400 * 7  # 7 days

ROLES = ("admin", "technician", "viewer")
