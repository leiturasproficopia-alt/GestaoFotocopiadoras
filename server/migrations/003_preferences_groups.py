from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            theme TEXT NOT NULL DEFAULT 'light',
            notifications INTEGER NOT NULL DEFAULT 1,
            dashboard_refresh INTEGER NOT NULL DEFAULT 30,
            language TEXT NOT NULL DEFAULT 'pt',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS device_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#0d6efd',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS device_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES device_groups(id),
            FOREIGN KEY (device_id) REFERENCES devices(id),
            UNIQUE(group_id, device_id)
        );

        CREATE INDEX IF NOT EXISTS idx_group_members_group ON device_group_members(group_id);
        CREATE INDEX IF NOT EXISTS idx_group_members_device ON device_group_members(device_id);
    """)
