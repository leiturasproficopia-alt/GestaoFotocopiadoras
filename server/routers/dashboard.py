from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_login
from server.database import get_db

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/dashboard")
@require_login
async def dashboard(request: Request):
    user = request.state.user
    with get_db() as conn:
        total_devices = conn.execute("SELECT COUNT(*) as c FROM devices").fetchone()["c"]
        online_devices = conn.execute("SELECT COUNT(*) as c FROM devices WHERE online=1").fetchone()["c"]
        offline_devices = conn.execute("SELECT COUNT(*) as c FROM devices WHERE online=0 AND last_seen IS NOT NULL").fetchone()["c"]
        total_agents = conn.execute("SELECT COUNT(*) as c FROM agents").fetchone()["c"]
        active_agents = conn.execute("SELECT COUNT(*) as c FROM agents WHERE active=1").fetchone()["c"]

        low_supplies = conn.execute("""
            SELECT d.ip, d.manufacturer, d.model, dc.description, dc.percent, dc.status
            FROM device_consumables dc
            JOIN devices d ON d.id = dc.device_id
            WHERE dc.percent IS NOT NULL AND dc.percent <= 20
            AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
            ORDER BY dc.percent ASC
            LIMIT 10
        """).fetchall()

        recent_errors = conn.execute("""
            SELECT d.ip, d.manufacturer, d.model, de.code, de.description, de.severity, de.collected_at
            FROM device_errors de
            JOIN devices d ON d.id = de.device_id
            ORDER BY de.collected_at DESC
            LIMIT 10
        """).fetchall()

        devices_by_manufacturer = conn.execute("""
            SELECT manufacturer, COUNT(*) as count
            FROM devices
            GROUP BY manufacturer
            ORDER BY count DESC
        """).fetchall()

        errors_by_severity = conn.execute("""
            SELECT severity, COUNT(*) as count
            FROM device_errors
            GROUP BY severity
            ORDER BY count DESC
        """).fetchall()

        avg_consumable_levels = conn.execute("""
            SELECT dc.description, ROUND(AVG(dc.percent), 1) as avg_percent, COUNT(*) as count
            FROM device_consumables dc
            WHERE dc.percent IS NOT NULL
            AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
            GROUP BY dc.description
            ORDER BY avg_percent ASC
            LIMIT 10
        """).fetchall()

        active_alerts = conn.execute(
            "SELECT COUNT(*) as c FROM alert_history WHERE acknowledged=0"
        ).fetchone()["c"]

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": offline_devices,
        "total_agents": total_agents,
        "active_agents": active_agents,
        "low_supplies": low_supplies,
        "recent_errors": recent_errors,
        "devices_by_manufacturer": devices_by_manufacturer,
        "errors_by_severity": errors_by_severity,
        "avg_consumable_levels": avg_consumable_levels,
        "active_alerts": active_alerts,
    })


@router.get("/api/dashboard/cards")
@require_login
async def dashboard_cards_fragment(request: Request):
    with get_db() as conn:
        total_devices = conn.execute("SELECT COUNT(*) as c FROM devices").fetchone()["c"]
        online_devices = conn.execute("SELECT COUNT(*) as c FROM devices WHERE online=1").fetchone()["c"]
        offline_devices = conn.execute("SELECT COUNT(*) as c FROM devices WHERE online=0 AND last_seen IS NOT NULL").fetchone()["c"]
        active_agents = conn.execute("SELECT COUNT(*) as c FROM agents WHERE active=1").fetchone()["c"]
        total_agents = conn.execute("SELECT COUNT(*) as c FROM agents").fetchone()["c"]
        active_alerts = conn.execute("SELECT COUNT(*) as c FROM alert_history WHERE acknowledged=0").fetchone()["c"]

    html = f"""
    <div class="col-md-3"><div class="card text-bg-primary"><div class="card-body"><div class="d-flex justify-content-between"><div><h6 class="card-title">Total Dispositivos</h6><h2>{total_devices}</h2></div><i class="bi bi-printer display-6 opacity-50"></i></div></div></div></div>
    <div class="col-md-3"><div class="card text-bg-success"><div class="card-body"><div class="d-flex justify-content-between"><div><h6 class="card-title">Online</h6><h2>{online_devices}</h2></div><i class="bi bi-check-circle display-6 opacity-50"></i></div></div></div></div>
    <div class="col-md-3"><div class="card text-bg-danger"><div class="card-body"><div class="d-flex justify-content-between"><div><h6 class="card-title">Offline</h6><h2>{offline_devices}</h2></div><i class="bi bi-x-circle display-6 opacity-50"></i></div></div></div></div>
    <div class="col-md-3"><div class="card text-bg-info"><div class="card-body"><div class="d-flex justify-content-between"><div><h6 class="card-title">Agentes Ativos</h6><h2>{active_agents} / {total_agents}</h2>{'<span class="badge bg-danger">' + str(active_alerts) + ' alertas</span>' if active_alerts > 0 else ''}</div><i class="bi bi-hdd-network display-6 opacity-50"></i></div></div></div></div>
    """
    return html


@router.get("/api/dashboard/low-supplies")
@require_login
async def dashboard_low_supplies_fragment(request: Request):
    with get_db() as conn:
        low_supplies = conn.execute("""
            SELECT d.ip, d.manufacturer, d.model, dc.description, dc.percent, dc.status
            FROM device_consumables dc
            JOIN devices d ON d.id = dc.device_id
            WHERE dc.percent IS NOT NULL AND dc.percent <= 20
            AND dc.id IN (SELECT MAX(id) FROM device_consumables GROUP BY device_id, description)
            ORDER BY dc.percent ASC LIMIT 10
        """).fetchall()

    rows = ""
    for s in low_supplies:
        color = "danger" if s["percent"] <= 5 else "warning" if s["percent"] <= 15 else "info"
        rows += f"""<tr><td>{s['ip']}</td><td>{s['manufacturer']}</td><td>{s['model']}</td><td>{s['description'] or 'N/D'}</td>
        <td><div class="progress" style="height:20px"><div class="progress-bar bg-{color}" style="width:{s['percent']}%">{s['percent']}%</div></div></td>
        <td><span class="badge bg-{color}">{s['status']}</span></td></tr>"""

    if not rows:
        return '<p class="text-muted mb-0">Nenhum consumivel com nivel baixo.</p>'

    return f"""<div class="table-responsive"><table class="table table-sm table-hover"><thead><tr><th>IP</th><th>Marca</th><th>Modelo</th><th>Consumivel</th><th>Nivel</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table></div>"""


@router.get("/api/dashboard/recent-errors")
@require_login
async def dashboard_recent_errors_fragment(request: Request):
    with get_db() as conn:
        recent_errors = conn.execute("""
            SELECT d.ip, d.manufacturer, d.model, de.code, de.description, de.severity, de.collected_at
            FROM device_errors de JOIN devices d ON d.id = de.device_id
            ORDER BY de.collected_at DESC LIMIT 10
        """).fetchall()

    rows = ""
    for e in recent_errors:
        color = "danger" if e["severity"] == "critical" else "warning" if e["severity"] == "warning" else "info"
        rows += f"""<tr><td>{e['collected_at'][:16]}</td><td>{e['ip']}</td><td>{e['model']}</td><td>{e['code'] or 'N/D'}</td><td>{e['description'] or 'N/D'}</td>
        <td><span class="badge bg-{color}">{e['severity']}</span></td></tr>"""

    if not rows:
        return '<p class="text-muted mb-0">Nenhum erro registado.</p>'

    return f"""<div class="table-responsive"><table class="table table-sm table-hover"><thead><tr><th>Data</th><th>IP</th><th>Modelo</th><th>Codigo</th><th>Descricao</th><th>Severidade</th></tr></thead><tbody>{rows}</tbody></table></div>"""
