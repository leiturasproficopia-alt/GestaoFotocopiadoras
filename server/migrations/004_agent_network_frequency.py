from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection):
    conn.executescript("""
        ALTER TABLE agents ADD COLUMN discovery_interval INTEGER NOT NULL DEFAULT 4;
        ALTER TABLE agents ADD COLUMN discovery_unit TEXT NOT NULL DEFAULT 'hours';
        ALTER TABLE agents ADD COLUMN counters_interval INTEGER NOT NULL DEFAULT 4;
        ALTER TABLE agents ADD COLUMN counters_unit TEXT NOT NULL DEFAULT 'hours';
        ALTER TABLE agents ADD COLUMN supplies_interval INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE agents ADD COLUMN supplies_unit TEXT NOT NULL DEFAULT 'hours';
        ALTER TABLE agents ADD COLUMN alerts_interval INTEGER NOT NULL DEFAULT 60;
        ALTER TABLE agents ADD COLUMN alerts_unit TEXT NOT NULL DEFAULT 'minutes';
        ALTER TABLE agents ADD COLUMN attributes_interval INTEGER NOT NULL DEFAULT 12;
        ALTER TABLE agents ADD COLUMN attributes_unit TEXT NOT NULL DEFAULT 'hours';

        CREATE TABLE IF NOT EXISTS agent_networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            ip_address TEXT NOT NULL,
            hostname TEXT DEFAULT '',
            ip_end TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            UNIQUE(agent_id, ip_address)
        );

        CREATE INDEX IF NOT EXISTS idx_agent_networks_agent ON agent_networks(agent_id);
    """)
