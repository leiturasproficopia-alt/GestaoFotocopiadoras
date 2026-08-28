from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection):
    conn.executescript("""
        ALTER TABLE agents ADD COLUMN server_url TEXT DEFAULT '';
    """)
