from __future__ import annotations

from server.database import get_db


def log_audit(
    user_id: int | None,
    username: str,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    ip_address: str = "",
    user_agent: str = "",
):
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO audit_log
                   (user_id, username, action, entity_type, entity_id, old_value, new_value, ip_address, user_agent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, action, entity_type, entity_id, old_value, new_value, ip_address, user_agent),
            )
    except Exception:
        pass
