from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection):
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN expires_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN ip_address TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN user_agent TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        UPDATE sessions SET expires_at = datetime(created_at, '+7 days')
        WHERE expires_at IS NULL
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
