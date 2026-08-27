from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse

from server.auth import require_login
from server.database import get_db

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/devices")
@require_login
async def export_devices(
    request: Request,
    search: str = Query("", alias="q"),
    manufacturer: str = Query("", alias="mfr"),
    status: str = Query("", alias="status"),
    agent_id: int = Query(0, alias="agent"),
):
    conditions = []
    params = []
    if search:
        conditions.append("(d.ip LIKE ? OR d.model LIKE ? OR d.serial_number LIKE ? OR d.hostname LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s, s])
    if manufacturer:
        conditions.append("d.manufacturer = ?")
        params.append(manufacturer)
    if status:
        conditions.append("d.status = ?")
        params.append(status)
    if agent_id:
        conditions.append("d.agent_id = ?")
        params.append(agent_id)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT d.ip, d.manufacturer, d.model, d.serial_number, d.hostname,
                   d.status, d.severity, d.online, d.last_seen, d.snmp_version,
                   a.name as agent_name, a.customer_name
            FROM devices d
            LEFT JOIN agents a ON a.id = d.agent_id
            {where}
            ORDER BY d.manufacturer, d.model, d.ip
        """, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["IP", "Marca", "Modelo", "Serial", "Hostname", "Estado", "Severidade", "Online", "Ultima Vez", "SNMP", "Agente", "Cliente"])
    for r in rows:
        writer.writerow([r["ip"], r["manufacturer"], r["model"], r["serial_number"], r["hostname"],
                         r["status"], r["severity"], "Sim" if r["online"] else "Nao", r["last_seen"] or "",
                         r["snmp_version"], r["agent_name"] or "", r["customer_name"] or ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dispositivos.csv"},
    )


@router.get("/errors")
@require_login
async def export_errors(
    request: Request,
    severity: str = Query("", alias="sev"),
):
    conditions = []
    params = []
    if severity:
        conditions.append("de.severity = ?")
        params.append(severity)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT de.code, de.description, de.severity, de.source, de.collected_at,
                   d.ip, d.manufacturer, d.model, d.hostname
            FROM device_errors de
            JOIN devices d ON d.id = de.device_id
            {where}
            ORDER BY de.collected_at DESC
        """, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data", "IP", "Marca", "Modelo", "Hostname", "Codigo", "Descricao", "Severidade", "Fonte"])
    for r in rows:
        writer.writerow([r["collected_at"], r["ip"], r["manufacturer"], r["model"], r["hostname"],
                         r["code"], r["description"], r["severity"], r["source"]])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=erros.csv"},
    )


@router.get("/consumables")
@require_login
async def export_consumables(
    request: Request,
    alert: str = Query("", alias="alert"),
):
    with get_db() as conn:
        if alert == "low":
            rows = conn.execute("""
                SELECT d.ip, d.manufacturer, d.model, d.hostname,
                       dc.description, dc.percent, dc.status, dc.level, dc.max_capacity, dc.collected_at
                FROM device_consumables dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.percent IS NOT NULL AND dc.percent <= 20
                AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
                ORDER BY dc.percent ASC
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT d.ip, d.manufacturer, d.model, d.hostname,
                       dc.description, dc.percent, dc.status, dc.level, dc.max_capacity, dc.collected_at
                FROM device_consumables dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
                ORDER BY d.manufacturer, d.model, dc.description
            """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["IP", "Marca", "Modelo", "Hostname", "Consumivel", "Percentagem", "Nivel", "Capacidade Max", "Estado", "Ultima Leitura"])
    for r in rows:
        writer.writerow([r["ip"], r["manufacturer"], r["model"], r["hostname"],
                         r["description"], r["percent"] or 0, r["level"] or 0, r["max_capacity"] or 0,
                         r["status"], r["collected_at"]])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=consumiveis.csv"},
    )
