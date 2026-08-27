from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

from server.database import get_db

MIGRATIONS_DIR = Path(__file__).parent

MIGRATION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def ensure_migration_table(conn: sqlite3.Connection):
    conn.executescript(MIGRATION_TABLE)


def get_applied(conn: sqlite3.Connection) -> set[str]:
    ensure_migration_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return {r["version"] for r in rows}


def get_pending(applied: set[str]) -> list[tuple[str, str, Path]]:
    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("0*.py")):
        version = f.stem.split("_")[0]
        name = "_".join(f.stem.split("_")[1:])
        if version not in applied:
            migrations.append((version, name, f))
    return migrations


def apply_migration(conn: sqlite3.Connection, version: str, name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"migration_{version}", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "up"):
        module.up(conn)

    conn.execute(
        "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
        (version, name),
    )
    conn.commit()


def run_migrations(db_path: str | Path | None = None):
    with get_db(db_path) as conn:
        ensure_migration_table(conn)
        applied = get_applied(conn)
        pending = get_pending(applied)

        for version, name, path in pending:
            apply_migration(conn, version, name, path)
