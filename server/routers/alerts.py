from __future__ import annotations

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_role, require_login
from server.database import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

RULE_TYPES = [
    ("consumable_low", "Consumivel Baixo"),
    ("error_critical", "Erro Critico"),
    ("device_offline", "Dispositivo Offline"),
    ("counter_threshold", "Limite de Contador"),
]

SEVERITIES = ["info", "warning", "critical"]


@router.get("/")
@require_login
async def alert_list(
    request: Request,
    sev: str = Query("", alias="sev"),
    ack: str = Query("", alias="ack"),
    page: int = Query(1, ge=1),
):
    user = request.state.user
    per_page = 30
    offset = (page - 1) * per_page
    conditions = []
    params = []

    if sev:
        conditions.append("ah.severity = ?")
        params.append(sev)
    if ack == "yes":
        conditions.append("ah.acknowledged = 1")
    elif ack == "no":
        conditions.append("ah.acknowledged = 0")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM alert_history ah {where}", params
        ).fetchone()["c"]

        alerts = conn.execute(f"""
            SELECT ah.*, ar.name as rule_name, ar.rule_type,
                   d.ip, d.manufacturer, d.model
            FROM alert_history ah
            JOIN alert_rules ar ON ar.id = ah.rule_id
            JOIN devices d ON d.id = ah.device_id
            {where}
            ORDER BY ah.acknowledged ASC, ah.triggered_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        active_count = conn.execute(
            "SELECT COUNT(*) as c FROM alert_history WHERE acknowledged=0"
        ).fetchone()["c"]

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(request, "alerts/list.html", {
        "user": user,
        "alerts": alerts,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filter_severity": sev,
        "filter_ack": ack,
        "active_count": active_count,
    })


@router.post("/{alert_id}/acknowledge")
@require_login
async def alert_acknowledge(request: Request, alert_id: int):
    user = request.state.user
    with get_db() as conn:
        conn.execute(
            "UPDATE alert_history SET acknowledged=1, acknowledged_by=?, acknowledged_at=datetime('now') WHERE id=?",
            (user["id"], alert_id),
        )
    return RedirectResponse("/alerts/", status_code=303)


@router.post("/acknowledge-all")
@require_login
async def alert_acknowledge_all(request: Request):
    user = request.state.user
    with get_db() as conn:
        conn.execute(
            "UPDATE alert_history SET acknowledged=1, acknowledged_by=?, acknowledged_at=datetime('now') WHERE acknowledged=0",
            (user["id"],),
        )
    return RedirectResponse("/alerts/", status_code=303)


@router.get("/rules")
@require_role("admin", "technician")
async def rule_list(request: Request):
    user = request.state.user
    with get_db() as conn:
        rules = conn.execute("""
            SELECT ar.*,
                   (SELECT COUNT(*) FROM alert_history ah WHERE ah.rule_id = ar.id) as trigger_count,
                   (SELECT COUNT(*) FROM alert_history ah WHERE ah.rule_id = ar.id AND ah.acknowledged = 0) as active_count
            FROM alert_rules ar
            ORDER BY ar.name
        """).fetchall()

    return templates.TemplateResponse(request, "alerts/rules.html", {
        "user": user,
        "rules": rules,
    })


@router.get("/rules/new")
@require_role("admin")
async def rule_new_form(request: Request):
    user = request.state.user
    return templates.TemplateResponse(request, "alerts/rule_form.html", {
        "user": user,
        "rule": None,
        "rule_types": RULE_TYPES,
        "severities": SEVERITIES,
    })


@router.post("/rules/new")
@require_role("admin")
async def rule_new_submit(
    request: Request,
    name: str = Form(...),
    rule_type: str = Form(...),
    threshold: int = Form(20),
    severity: str = Form("warning"),
    description: str = Form(""),
):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO alert_rules (name, rule_type, threshold, severity, description) VALUES (?, ?, ?, ?, ?)",
            (name, rule_type, threshold, severity, description),
        )
    return RedirectResponse("/alerts/rules", status_code=303)


@router.get("/rules/{rule_id}/edit")
@require_role("admin")
async def rule_edit_form(request: Request, rule_id: int):
    user = request.state.user
    with get_db() as conn:
        rule = conn.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,)).fetchone()
    if not rule:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "alerts/rule_form.html", {
        "user": user,
        "rule": rule,
        "rule_types": RULE_TYPES,
        "severities": SEVERITIES,
    })


@router.post("/rules/{rule_id}/edit")
@require_role("admin")
async def rule_edit_submit(
    request: Request,
    rule_id: int,
    name: str = Form(...),
    rule_type: str = Form(...),
    threshold: int = Form(20),
    severity: str = Form("warning"),
    description: str = Form(""),
    active: int = Form(1),
):
    with get_db() as conn:
        conn.execute(
            "UPDATE alert_rules SET name=?, rule_type=?, threshold=?, severity=?, description=?, active=?, updated_at=datetime('now') WHERE id=?",
            (name, rule_type, threshold, severity, description, active, rule_id),
        )
    return RedirectResponse("/alerts/rules", status_code=303)


@router.post("/rules/{rule_id}/delete")
@require_role("admin")
async def rule_delete(request: Request, rule_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    return RedirectResponse("/alerts/rules", status_code=303)


def check_alerts():
    with get_db() as conn:
        rules = conn.execute("SELECT * FROM alert_rules WHERE active=1").fetchall()

        for rule in rules:
            if rule["rule_type"] == "consumable_low":
                _check_consumable_low(conn, rule)
            elif rule["rule_type"] == "error_critical":
                _check_error_critical(conn, rule)
            elif rule["rule_type"] == "device_offline":
                _check_device_offline(conn, rule)


def _check_consumable_low(conn, rule):
    items = conn.execute("""
        SELECT dc.device_id, dc.description, dc.percent, d.ip
        FROM device_consumables dc
        JOIN devices d ON d.id = dc.device_id
        WHERE dc.percent IS NOT NULL AND dc.percent <= ?
        AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
    """, (rule["threshold"],)).fetchall()

    for item in items:
        exists = conn.execute(
            "SELECT 1 FROM alert_history WHERE rule_id=? AND device_id=? AND acknowledged=0",
            (rule["id"], item["device_id"]),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO alert_history (rule_id, device_id, message, severity) VALUES (?, ?, ?, ?)",
                (rule["id"], item["device_id"],
                 f"{item['description']} a {item['percent']}% no dispositivo {item['ip']}",
                 rule["severity"]),
            )


def _check_error_critical(conn, rule):
    items = conn.execute("""
        SELECT de.device_id, de.code, de.description, d.ip
        FROM device_errors de
        JOIN devices d ON d.id = de.device_id
        WHERE de.severity = 'critical'
        AND de.collected_at > datetime('now', '-1 hour')
    """).fetchall()

    for item in items:
        exists = conn.execute(
            "SELECT 1 FROM alert_history WHERE rule_id=? AND device_id=? AND message=? AND acknowledged=0",
            (rule["id"], item["device_id"], f"Erro critico {item['code']}: {item['description']} no {item['ip']}"),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO alert_history (rule_id, device_id, message, severity) VALUES (?, ?, ?, ?)",
                (rule["id"], item["device_id"],
                 f"Erro critico {item['code']}: {item['description']} no {item['ip']}",
                 rule["severity"]),
            )


def _check_device_offline(conn, rule):
    items = conn.execute("""
        SELECT d.id as device_id, d.ip, d.last_seen
        FROM devices d
        WHERE d.online = 0
        AND d.last_seen IS NOT NULL
        AND d.last_seen < datetime('now', ? || ' hours')
    """, (f"-{rule['threshold']}",)).fetchall()

    for item in items:
        exists = conn.execute(
            "SELECT 1 FROM alert_history WHERE rule_id=? AND device_id=? AND acknowledged=0",
            (rule["id"], item["device_id"]),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO alert_history (rule_id, device_id, message, severity) VALUES (?, ?, ?, ?)",
                (rule["id"], item["device_id"],
                 f"Dispositivo {item['ip']} offline desde {item['last_seen']}",
                 rule["severity"]),
            )
