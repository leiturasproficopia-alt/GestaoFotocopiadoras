from __future__ import annotations

import json

from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_login
from server.database import get_db

router = APIRouter(prefix="/devices", tags=["devices"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_login
async def device_list(
    request: Request,
    search: str = Query("", alias="q"),
    manufacturer: str = Query("", alias="mfr"),
    status: str = Query("", alias="status"),
    agent_id: int = Query(0, alias="agent"),
    page: int = Query(1, ge=1),
):
    user = request.state.user
    per_page = 20
    offset = (page - 1) * per_page
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
        total = conn.execute(f"SELECT COUNT(*) as c FROM devices d {where}", params).fetchone()["c"]
        devices = conn.execute(f"""
            SELECT d.*, a.name as agent_name
            FROM devices d
            LEFT JOIN agents a ON a.id = d.agent_id
            {where}
            ORDER BY d.manufacturer, d.model, d.ip
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        manufacturers = conn.execute(
            "SELECT DISTINCT manufacturer FROM devices ORDER BY manufacturer"
        ).fetchall()
        agents = conn.execute("SELECT id, name FROM agents ORDER BY name").fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(request, "devices/list.html", {
        "user": user,
        "devices": devices,
        "manufacturers": [r["manufacturer"] for r in manufacturers],
        "agents": agents,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "search": search,
        "filter_manufacturer": manufacturer,
        "filter_status": status,
        "filter_agent_id": agent_id,
    })


@router.get("/{device_id}")
@require_login
async def device_detail(request: Request, device_id: int):
    user = request.state.user
    with get_db() as conn:
        device = conn.execute("""
            SELECT d.*, a.name as agent_name, a.customer_name
            FROM devices d
            LEFT JOIN agents a ON a.id = d.agent_id
            WHERE d.id = ?
        """, (device_id,)).fetchone()

        if not device:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Dispositivo nao encontrado")

        counters = conn.execute("""
            SELECT * FROM device_counters
            WHERE device_id = ?
            ORDER BY collected_at DESC, counter_name
            LIMIT 100
        """, (device_id,)).fetchall()

        consumables = conn.execute("""
            SELECT * FROM device_consumables
            WHERE device_id = ?
            AND id IN (SELECT MAX(id) FROM device_consumables WHERE device_id=? GROUP BY description)
            ORDER BY percent ASC
        """, (device_id, device_id)).fetchall()

        errors = conn.execute("""
            SELECT * FROM device_errors
            WHERE device_id = ?
            ORDER BY collected_at DESC
            LIMIT 50
        """, (device_id,)).fetchall()

        status_history = conn.execute("""
            SELECT * FROM device_status_history
            WHERE device_id = ?
            ORDER BY collected_at DESC
            LIMIT 50
        """, (device_id,)).fetchall()

        counter_history = conn.execute("""
            SELECT counter_name, counter_value, collected_at
            FROM device_counters
            WHERE device_id = ?
            ORDER BY collected_at ASC
        """, (device_id,)).fetchall()

    chart_data = {}
    for row in counter_history:
        name = row["counter_name"]
        if name not in chart_data:
            chart_data[name] = {"labels": [], "values": []}
        chart_data[name]["labels"].append(row["collected_at"])
        chart_data[name]["values"].append(row["counter_value"])

    return templates.TemplateResponse(request, "devices/detail.html", {
        "user": user,
        "device": device,
        "counters": counters,
        "consumables": consumables,
        "errors": errors,
        "status_history": status_history,
        "counter_history": counter_history,
        "chart_data_json": json.dumps(chart_data),
    })
