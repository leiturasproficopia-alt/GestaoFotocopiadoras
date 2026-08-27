from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from server.config import DATA_DIR
from server.database import get_db

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)


def create_backup(custom_name: str = "") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{custom_name}_{timestamp}.db" if custom_name else f"backup_{timestamp}.db"
    backup_path = BACKUP_DIR / name

    with get_db() as conn:
        conn.execute(f"VACUUM INTO '{backup_path}'")

    return backup_path


def list_backups() -> list[dict]:
    backups = []
    for f in sorted(BACKUP_DIR.glob("*.db"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "path": str(f),
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return backups


def restore_backup(backup_path: str | Path) -> bool:
    from server.config import DATABASE_PATH
    source = Path(backup_path)
    if not source.exists():
        return False
    shutil.copy2(str(source), str(DATABASE_PATH))
    return True


def delete_backup(backup_path: str | Path) -> bool:
    path = Path(backup_path)
    if path.exists() and str(path).startswith(str(BACKUP_DIR)):
        path.unlink()
        return True
    return False
