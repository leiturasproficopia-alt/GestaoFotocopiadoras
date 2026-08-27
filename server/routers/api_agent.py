from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from server.database import get_db

router = APIRouter(prefix="/api/agent", tags=["api-agent"])


class CounterData(BaseModel):
    name: str
    value: int | None = None
    source: str = ""
    oid: str = ""
    unit: str = "pages"


class ConsumableData(BaseModel):
    description: str = ""
    type_code: int | None = None
    level: int | None = None
    max_capacity: int | None = None
    percent: int | None = None
    status: str = "ok"
    source: str = ""


class ErrorData(BaseModel):
    code: str = ""
    description: str = ""
    severity: str = "info"
    source: str = ""

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if isinstance(obj, dict) and "description" in obj:
            obj["description"] = str(obj["description"])
        return super().model_validate(obj, **kwargs)


class StatusData(BaseModel):
    status: str = "unknown"
    severity: str = "unknown"
    source: str = ""
    code: str | None = None
    description: str | None = None


class DeviceData(BaseModel):
    ip: str
    manufacturer: str = "Desconhecido"
    model: str = ""
    serial_number: str = ""
    hostname: str = ""
    sys_object_id: str = ""
    firmware: str = ""
    sys_location: str = ""
    sys_contact: str = ""
    snmp_version: str = "v2c"
    status: StatusData | None = None
    counters: list[CounterData] = []
    consumables: list[ConsumableData] = []
    errors: list[ErrorData] = []


class SnapshotPayload(BaseModel):
    agent_id: str
    devices: list[DeviceData] = []


@router.post("/snapshots")
async def receive_snapshot(request: Request, payload: SnapshotPayload):
    now = datetime.now(timezone.utc).isoformat()
    token = _extract_token(request)

    with get_db() as conn:
        agent = conn.execute(
            "SELECT id, active FROM agents WHERE agent_id=? AND api_token=?",
            (payload.agent_id, token),
        ).fetchone()

        if not agent:
            raise HTTPException(status_code=401, detail="Agente nao autorizado")
        if not agent["active"]:
            raise HTTPException(status_code=403, detail="Agente desativado")

        agent_db_id = agent["id"]
        conn.execute(
            "UPDATE agents SET last_heartbeat=?, updated_at=datetime('now') WHERE id=?",
            (now, agent_db_id),
        )

        devices_processed = 0
        for dev in payload.devices:
            _upsert_device(conn, agent_db_id, dev, now)
            devices_processed += 1

    return {"status": "ok", "devices_processed": devices_processed}


@router.post("/heartbeat")
async def heartbeat(request: Request):
    token = _extract_token(request)
    body = await request.json()
    agent_id = body.get("agent_id", "")

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        agent = conn.execute(
            "SELECT id FROM agents WHERE agent_id=? AND api_token=?",
            (agent_id, token),
        ).fetchone()

        if not agent:
            raise HTTPException(status_code=401, detail="Agente nao autorizado")

        conn.execute(
            "UPDATE agents SET last_heartbeat=?, updated_at=datetime('now') WHERE id=?",
            (now, agent["id"]),
        )

    return {"status": "ok"}


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return ""


def _upsert_device(conn, agent_db_id: int, dev: DeviceData, now: str):
    existing = conn.execute(
        "SELECT id FROM devices WHERE agent_id=? AND ip=?",
        (agent_db_id, dev.ip),
    ).fetchone()

    if existing:
        device_id = existing["id"]
        conn.execute("""
            UPDATE devices SET
                manufacturer=?, model=?, serial_number=?, hostname=?,
                sys_object_id=?, firmware=?, sys_location=?, sys_contact=?,
                snmp_version=?, status=?, severity=?, online=?,
                last_seen=?, updated_at=datetime('now')
            WHERE id=?
        """, (
            dev.manufacturer, dev.model, dev.serial_number, dev.hostname,
            dev.sys_object_id, dev.firmware, dev.sys_location, dev.sys_contact,
            dev.snmp_version,
            dev.status.status if dev.status else "unknown",
            dev.status.severity if dev.status else "unknown",
            1 if dev.status and dev.status.status == "online" else 0,
            now, device_id,
        ))
    else:
        cursor = conn.execute("""
            INSERT INTO devices (agent_id, ip, manufacturer, model, serial_number,
                hostname, sys_object_id, firmware, sys_location, sys_contact,
                snmp_version, status, severity, online, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_db_id, dev.ip, dev.manufacturer, dev.model, dev.serial_number,
            dev.hostname, dev.sys_object_id, dev.firmware, dev.sys_location, dev.sys_contact,
            dev.snmp_version,
            dev.status.status if dev.status else "unknown",
            dev.status.severity if dev.status else "unknown",
            1 if dev.status and dev.status.status == "online" else 0,
            now,
        ))
        device_id = cursor.lastrowid

    if dev.counters:
        conn.execute("DELETE FROM device_counters WHERE device_id=?", (device_id,))
        for c in dev.counters:
            conn.execute("""
                INSERT INTO device_counters (device_id, counter_name, counter_value, source, oid, unit, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (device_id, c.name, c.value, c.source, c.oid, c.unit, now))

    if dev.consumables:
        conn.execute("DELETE FROM device_consumables WHERE device_id=?", (device_id,))
        for cs in dev.consumables:
            conn.execute("""
                INSERT INTO device_consumables (device_id, description, type_code, level, max_capacity, percent, status, source, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (device_id, cs.description, cs.type_code, cs.level, cs.max_capacity, cs.percent, cs.status, cs.source, now))

    if dev.errors:
        conn.execute("DELETE FROM device_errors WHERE device_id=?", (device_id,))
        for e in dev.errors:
            conn.execute("""
                INSERT INTO device_errors (device_id, code, description, severity, source, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device_id, e.code, e.description, e.severity, e.source, now))

    if dev.status:
        conn.execute("""
            INSERT INTO device_status_history (device_id, status, severity, source, code, description, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (device_id, dev.status.status, dev.status.severity, dev.status.source, dev.status.code, dev.status.description, now))
