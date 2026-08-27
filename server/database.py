from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from server.config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    customer_name TEXT DEFAULT '',
    api_token TEXT NOT NULL,
    last_heartbeat TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    ip TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT 'Desconhecido',
    model TEXT DEFAULT '',
    serial_number TEXT DEFAULT '',
    hostname TEXT DEFAULT '',
    sys_object_id TEXT DEFAULT '',
    firmware TEXT DEFAULT '',
    sys_location TEXT DEFAULT '',
    sys_contact TEXT DEFAULT '',
    snmp_version TEXT DEFAULT 'v2c',
    status TEXT NOT NULL DEFAULT 'unknown',
    severity TEXT NOT NULL DEFAULT 'unknown',
    online INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    UNIQUE(agent_id, ip)
);

CREATE TABLE IF NOT EXISTS device_counters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    counter_name TEXT NOT NULL,
    counter_value INTEGER,
    source TEXT NOT NULL DEFAULT '',
    oid TEXT DEFAULT '',
    unit TEXT NOT NULL DEFAULT 'pages',
    collected_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS device_consumables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    description TEXT DEFAULT '',
    type_code INTEGER,
    level INTEGER,
    max_capacity INTEGER,
    percent INTEGER,
    status TEXT NOT NULL DEFAULT 'ok',
    source TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS device_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    code TEXT DEFAULT '',
    description TEXT DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS device_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    code TEXT,
    description TEXT,
    collected_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);

CREATE INDEX IF NOT EXISTS idx_devices_agent ON devices(agent_id);
CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
CREATE INDEX IF NOT EXISTS idx_counters_device ON device_counters(device_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_counters_name ON device_counters(device_id, counter_name);
CREATE INDEX IF NOT EXISTS idx_consumables_device ON device_consumables(device_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_errors_device ON device_errors(device_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_status_device ON device_status_history(device_id, collected_at);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    threshold INTEGER NOT NULL DEFAULT 20,
    severity TEXT NOT NULL DEFAULT 'warning',
    description TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_by INTEGER,
    acknowledged_at TEXT,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (rule_id) REFERENCES alert_rules(id),
    FOREIGN KEY (device_id) REFERENCES devices(id),
    FOREIGN KEY (acknowledged_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    cost_per_copy REAL DEFAULT 0.0,
    monthly_cost REAL DEFAULT 0.0,
    included_pages INTEGER DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    sla_hours INTEGER DEFAULT 24,
    notes TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contract_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    UNIQUE(contract_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_alert_history_rule ON alert_history(rule_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_device ON alert_history(device_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_ack ON alert_history(acknowledged);
CREATE INDEX IF NOT EXISTS idx_contract_agents_contract ON contract_agents(contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_agents_agent ON contract_agents(agent_id);
"""


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = str(db_path or DATABASE_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path: str | Path | None = None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database(db_path: str | Path | None = None):
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA)
