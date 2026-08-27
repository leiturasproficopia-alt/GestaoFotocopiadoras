from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_role
from server.database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_role("admin", "technician")
async def reports_page(request: Request):
    user = request.state.user
    with get_db() as conn:
        customers = conn.execute(
            "SELECT DISTINCT customer_name FROM agents WHERE customer_name != '' ORDER BY customer_name"
        ).fetchall()
    return templates.TemplateResponse(request, "reports/page.html", {
        "user": user,
        "customers": [r["customer_name"] for r in customers],
    })


@router.get("/monthly")
@require_role("admin", "technician")
async def report_monthly(
    request: Request,
    customer: str = Query("", alias="customer"),
    month: str = Query("", alias="month"),
):
    user = request.state.user
    if not month:
        month = datetime.now().strftime("%Y-%m")

    with get_db() as conn:
        if customer:
            agents = conn.execute(
                "SELECT id, name FROM agents WHERE customer_name=? ORDER BY name", (customer,)
            ).fetchall()
        else:
            agents = conn.execute("SELECT id, name, customer_name FROM agents ORDER BY customer_name, name").fetchall()

        agent_ids = [a["id"] for a in agents]

        report_data = []
        for agent in agents:
            if customer:
                devices = conn.execute(
                    "SELECT id, ip, model, manufacturer FROM devices WHERE agent_id=?", (agent["id"],)
                ).fetchall()
            else:
                devices = conn.execute(
                    "SELECT id, ip, model, manufacturer, agent_id FROM devices WHERE agent_id=?", (agent["id"],)
                ).fetchall()

            for dev in devices:
                counters = conn.execute("""
                    SELECT counter_name, counter_value, collected_at
                    FROM device_counters
                    WHERE device_id = ?
                    AND collected_at LIKE ?
                    ORDER BY collected_at
                """, (dev["id"], f"{month}%")).fetchall()

                consumables = conn.execute("""
                    SELECT description, percent, collected_at
                    FROM device_consumables
                    WHERE device_id = ?
                    AND id IN (SELECT MAX(id) FROM device_consumables WHERE device_id=? GROUP BY description)
                """, (dev["id"], dev["id"])).fetchall()

                errors = conn.execute("""
                    SELECT code, description, severity, collected_at
                    FROM device_errors
                    WHERE device_id = ?
                    AND collected_at LIKE ?
                    ORDER BY collected_at
                """, (dev["id"], f"{month}%")).fetchall()

                total_prints = 0
                for c in counters:
                    if c["counter_name"] and "total" in c["counter_name"].lower():
                        total_prints = c["counter_value"]
                        break

                report_data.append({
                    "agent_name": agent["name"],
                    "customer_name": agent.get("customer_name", customer),
                    "device_ip": dev["ip"],
                    "device_model": dev["model"],
                    "device_manufacturer": dev["manufacturer"],
                    "total_prints": total_prints,
                    "consumables": [{"name": c["description"], "level": c["percent"]} for c in consumables],
                    "errors_count": len(errors),
                    "errors_critical": len([e for e in errors if e["severity"] == "critical"]),
                })

        total_prints_all = sum(d["total_prints"] for d in report_data)
        total_errors_all = sum(d["errors_count"] for d in report_data)
        total_devices = len(report_data)

    html = _render_report_html(report_data, month, customer, total_prints_all, total_errors_all, total_devices)

    return StreamingResponse(
        iter([html]),
        media_type="text/html",
        headers={"Content-Disposition": f"inline; filename=relatorio_{month}.html"},
    )


@router.get("/monthly/csv")
@require_role("admin", "technician")
async def report_monthly_csv(
    request: Request,
    customer: str = Query("", alias="customer"),
    month: str = Query("", alias="month"),
):
    import csv
    import io

    if not month:
        month = datetime.now().strftime("%Y-%m")

    with get_db() as conn:
        if customer:
            agents = conn.execute(
                "SELECT id, name FROM agents WHERE customer_name=? ORDER BY name", (customer,)
            ).fetchall()
        else:
            agents = conn.execute("SELECT id, name, customer_name FROM agents ORDER BY customer_name, name").fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Cliente", "Agente", "IP", "Modelo", "Marca", "Total Impressoes", "Erros Total", "Erros Criticos"])

        for agent in agents:
            devices = conn.execute(
                "SELECT id, ip, model, manufacturer FROM devices WHERE agent_id=?", (agent["id"],)
            ).fetchall()

            for dev in devices:
                counters = conn.execute("""
                    SELECT counter_name, counter_value FROM device_counters
                    WHERE device_id = ? AND collected_at LIKE ?
                """, (dev["id"], f"{month}%")).fetchall()

                errors = conn.execute("""
                    SELECT severity FROM device_errors
                    WHERE device_id = ? AND collected_at LIKE ?
                """, (dev["id"], f"{month}%")).fetchall()

                total_prints = 0
                for c in counters:
                    if c["counter_name"] and "total" in c["counter_name"].lower():
                        total_prints = c["counter_value"]
                        break

                writer.writerow([
                    agent.get("customer_name", customer), agent["name"],
                    dev["ip"], dev["model"], dev["manufacturer"],
                    total_prints, len(errors), len([e for e in errors if e["severity"] == "critical"]),
                ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=relatorio_{month}.csv"},
    )


def _render_report_html(data, month, customer, total_prints, total_errors, total_devices):
    year, mon = month.split("-")
    month_names = ["", "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
                   "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    month_name = month_names[int(mon)]

    rows = ""
    for d in data:
        cons_html = ""
        for c in d["consumables"]:
            color = "#dc3545" if c["level"] and c["level"] <= 10 else "#ffc107" if c["level"] and c["level"] <= 25 else "#198754"
            cons_html += f'<div style="margin:2px 0"><small>{c["name"]}: <span style="color:{color}">{c["level"] or 0}%</span></small></div>'

        rows += f"""
        <tr>
            <td>{d['customer_name']}</td>
            <td>{d['agent_name']}</td>
            <td>{d['device_ip']}</td>
            <td>{d['device_manufacturer']} {d['device_model']}</td>
            <td style="text-align:right">{d['total_prints']}</td>
            <td>{cons_html or '<small class="text-muted">N/D</small>'}</td>
            <td style="text-align:right">{d['errors_count']}</td>
            <td style="text-align:right">{d['errors_critical']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Relatorio {month_name} {year}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
        h1 {{ color: #0d6efd; border-bottom: 2px solid #0d6efd; padding-bottom: 10px; }}
        h2 {{ color: #666; margin-top: 30px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px 25px; text-align: center; }}
        .summary-card h3 {{ margin: 0; font-size: 28px; color: #0d6efd; }}
        .summary-card p {{ margin: 5px 0 0; color: #666; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }}
        th {{ background: #343a40; color: white; padding: 8px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #dee2e6; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        .footer {{ margin-top: 40px; text-align: center; color: #999; font-size: 11px; border-top: 1px solid #eee; padding-top: 10px; }}
        @media print {{ body {{ margin: 20px; }} }}
    </style>
</head>
<body>
    <h1>Relatorio Mensal - {month_name} {year}</h1>
    <p><strong>Cliente:</strong> {customer or 'Todos'}</p>
    <p><strong>Data de geracao:</strong> {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>

    <div class="summary">
        <div class="summary-card">
            <h3>{total_devices}</h3>
            <p>Dispositivos</p>
        </div>
        <div class="summary-card">
            <h3>{total_prints:,}</h3>
            <p>Total Impressoes</p>
        </div>
        <div class="summary-card">
            <h3>{total_errors}</h3>
            <p>Erros</p>
        </div>
    </div>

    <h2>Detalhe por Dispositivo</h2>
    <table>
        <thead>
            <tr>
                <th>Cliente</th>
                <th>Agente</th>
                <th>IP</th>
                <th>Dispositivo</th>
                <th style="text-align:right">Impressoes</th>
                <th>Consumiveis</th>
                <th style="text-align:right">Erros</th>
                <th style="text-align:right">Criticos</th>
            </tr>
        </thead>
        <tbody>
            {rows if rows else '<tr><td colspan="8" style="text-align:center;color:#999">Sem dados para este periodo.</td></tr>'}
        </tbody>
    </table>

    <div class="footer">
        Gestao de Fotocopiadoras - Relatorio gerado automaticamente
    </div>
</body>
</html>"""
