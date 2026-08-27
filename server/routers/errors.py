from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_login
from server.database import get_db

router = APIRouter(prefix="/errors", tags=["errors"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_login
async def error_list(
    request: Request,
    severity: str = Query("", alias="sev"),
    page: int = Query(1, ge=1),
):
    user = request.state.user
    per_page = 30
    offset = (page - 1) * per_page
    conditions = []
    params = []

    if severity:
        conditions.append("de.severity = ?")
        params.append(severity)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM device_errors de {where}", params
        ).fetchone()["c"]

        errors = conn.execute(f"""
            SELECT de.*, d.ip, d.manufacturer, d.model, d.hostname
            FROM device_errors de
            JOIN devices d ON d.id = de.device_id
            {where}
            ORDER BY de.collected_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(request, "errors/list.html", {
        "user": user,
        "errors": errors,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filter_severity": severity,
    })
