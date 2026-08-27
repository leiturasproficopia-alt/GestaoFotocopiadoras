from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_login
from server.database import get_db

router = APIRouter(prefix="/counters", tags=["counters"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_login
async def counters_list(request: Request):
    user = request.state.user
    with get_db() as conn:
        devices = conn.execute("""
            SELECT d.id, d.ip, d.manufacturer, d.model, d.serial_number, d.hostname,
                   a.name as agent_name
            FROM devices d
            LEFT JOIN agents a ON d.agent_id = a.id
            ORDER BY d.ip
        """).fetchall()

        latest = conn.execute("""
            SELECT dc.device_id, dc.counter_name, dc.counter_value, dc.unit, dc.collected_at
            FROM device_counters dc
            INNER JOIN (
                SELECT device_id, counter_name, MAX(collected_at) as max_at
                FROM device_counters
                GROUP BY device_id, counter_name
            ) latest ON dc.device_id = latest.device_id
                AND dc.counter_name = latest.counter_name
                AND dc.collected_at = latest.max_at
            ORDER BY dc.device_id, dc.counter_name
        """).fetchall()

    device_data = []
    for d in devices:
        counters = {}
        max_date = None
        for c in latest:
            if c["device_id"] == d["id"]:
                counters[c["counter_name"]] = c["counter_value"]
                if c["collected_at"] and (not max_date or c["collected_at"] > max_date):
                    max_date = c["collected_at"]
        device_data.append({
            "device": d,
            "counters": counters,
            "last_update": max_date,
        })

    return templates.TemplateResponse(request, "counters/list.html", {
        "user": user,
        "device_data": device_data,
    })


@router.get("/history")
@require_login
async def counters_history(
    request: Request,
    device_id: int = Query(None),
    days: int = Query(30),
):
    user = request.state.user
    with get_db() as conn:
        if device_id:
            device = conn.execute(
                "SELECT id, ip, manufacturer, model FROM devices WHERE id=?",
                (device_id,),
            ).fetchone()
            devices = [device] if device else []
        else:
            devices = conn.execute(
                "SELECT id, ip, manufacturer, model FROM devices ORDER BY ip"
            ).fetchall()

        all_rows = []
        for d in devices:
            rows = conn.execute("""
                SELECT dc.counter_name, dc.counter_value, dc.unit, dc.collected_at,
                       d.ip, d.manufacturer, d.model
                FROM device_counters dc
                JOIN devices d ON dc.device_id = d.id
                WHERE dc.device_id = ?
                ORDER BY dc.collected_at DESC
                LIMIT 500
            """, (d["id"],)).fetchall()
            all_rows.extend(rows)

    return templates.TemplateResponse(request, "counters/history.html", {
        "user": user,
        "devices": devices,
        "selected_device_id": device_id,
        "rows": all_rows,
        "days": days,
    })


@router.get("/export")
@require_login
async def counters_export(
    request: Request,
    device_id: int = Query(None),
):
    user = request.state.user
    with get_db() as conn:
        if device_id:
            rows = conn.execute("""
                SELECT dc.counter_name, dc.counter_value, dc.unit, dc.collected_at,
                       d.ip, d.manufacturer, d.model
                FROM device_counters dc
                JOIN devices d ON dc.device_id = d.id
                WHERE dc.device_id = ?
                ORDER BY dc.collected_at DESC
            """, (device_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT dc.counter_name, dc.counter_value, dc.unit, dc.collected_at,
                       d.ip, d.manufacturer, d.model
                FROM device_counters dc
                JOIN devices d ON dc.device_id = d.id
                ORDER BY dc.collected_at DESC
            """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data", "IP", "Fabricante", "Modelo", "Contador", "Valor", "Unidade"])
    for r in rows:
        writer.writerow([
            r["collected_at"], r["ip"], r["manufacturer"], r["model"],
            r["counter_name"], r["counter_value"], r["unit"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contadores.csv"},
    )
