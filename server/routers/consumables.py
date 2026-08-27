from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_login
from server.database import get_db

router = APIRouter(prefix="/consumables", tags=["consumables"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_login
async def consumables_overview(
    request: Request,
    alert: str = Query("", alias="alert"),
    page: int = Query(1, ge=1),
):
    user = request.state.user
    per_page = 30
    offset = (page - 1) * per_page
    with get_db() as conn:
        if alert == "low":
            total = conn.execute("""
                SELECT COUNT(*) as c FROM device_consumables dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.percent IS NOT NULL AND dc.percent <= 20
                AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
            """).fetchone()["c"]
            items = conn.execute("""
                SELECT d.ip, d.manufacturer, d.model, d.hostname,
                       dc.description, dc.percent, dc.status, dc.level, dc.max_capacity,
                       dc.collected_at
                FROM device_consumables dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.percent IS NOT NULL AND dc.percent <= 20
                AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
                ORDER BY dc.percent ASC
                LIMIT ? OFFSET ?
            """, (per_page, offset)).fetchall()
        else:
            total = conn.execute("""
                SELECT COUNT(*) as c FROM device_consumables dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
            """).fetchone()["c"]
            items = conn.execute("""
                SELECT d.ip, d.manufacturer, d.model, d.hostname,
                       dc.description, dc.percent, dc.status, dc.level, dc.max_capacity,
                       dc.collected_at
                FROM device_consumables dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
                ORDER BY d.manufacturer, d.model, dc.description
                LIMIT ? OFFSET ?
            """, (per_page, offset)).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(request, "consumables/status.html", {
        "user": user,
        "consumables": items,
        "filter_alert": alert,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    })
