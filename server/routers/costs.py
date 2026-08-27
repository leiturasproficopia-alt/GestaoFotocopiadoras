from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

import csv
import io

from server.config import BASE_DIR
from server.auth import require_role
from server.database import get_db

router = APIRouter(prefix="/costs", tags=["costs"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_role("admin", "technician")
async def costs_dashboard(request: Request):
    user = request.state.user
    with get_db() as conn:
        customers = conn.execute("""
            SELECT a.customer_name,
                   COUNT(DISTINCT d.id) as device_count,
                   COUNT(DISTINCT a.id) as agent_count
            FROM agents a
            LEFT JOIN devices d ON d.agent_id = a.id
            WHERE a.customer_name != ''
            GROUP BY a.customer_name
            ORDER BY a.customer_name
        """).fetchall()

        cost_data = []
        for cust in customers:
            pages = conn.execute("""
                SELECT COALESCE(SUM(dc.counter_value), 0) as total_pages
                FROM device_counters dc
                JOIN devices d ON d.id = dc.device_id
                JOIN agents a ON a.id = d.agent_id
                WHERE a.customer_name = ?
                AND dc.counter_name LIKE '%Total%'
            """, (cust["customer_name"],)).fetchone()["total_pages"]

            contract = conn.execute("""
                SELECT c.cost_per_copy, c.monthly_cost, c.included_pages
                FROM contracts c
                WHERE c.customer_name = ? AND c.active = 1
                LIMIT 1
            """, (cust["customer_name"],)).fetchone()

            cost_per_copy = contract["cost_per_copy"] if contract else 0
            monthly_base = contract["monthly_cost"] if contract else 0
            included = contract["included_pages"] if contract else 0

            overage = max(0, pages - included)
            copy_cost = overage * cost_per_copy
            total_cost = monthly_base + copy_cost

            cost_data.append({
                "customer_name": cust["customer_name"],
                "device_count": cust["device_count"],
                "agent_count": cust["agent_count"],
                "total_pages": pages,
                "cost_per_copy": cost_per_copy,
                "monthly_base": monthly_base,
                "included_pages": included,
                "overage_pages": overage,
                "copy_cost": copy_cost,
                "total_cost": total_cost,
            })

        total_cost_all = sum(c["total_cost"] for c in cost_data)
        total_pages_all = sum(c["total_pages"] for c in cost_data)

    return templates.TemplateResponse(request, "costs/dashboard.html", {
        "user": user,
        "cost_data": cost_data,
        "total_cost_all": total_cost_all,
        "total_pages_all": total_pages_all,
    })


@router.get("/csv")
@require_role("admin", "technician")
async def costs_csv(request: Request):
    with get_db() as conn:
        customers = conn.execute("""
            SELECT a.customer_name
            FROM agents a
            WHERE a.customer_name != ''
            GROUP BY a.customer_name
            ORDER BY a.customer_name
        """).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Cliente", "Dispositivos", "Agentes", "Total Paginas", "Custo/Copia", "Custo Base", "Paginas Incluidas", "Excedente", "Custo Copias", "Custo Total"])

        for cust in customers:
            cn = cust["customer_name"]
            devs = conn.execute("SELECT COUNT(*) as c FROM devices d JOIN agents a ON a.id=d.agent_id WHERE a.customer_name=?", (cn,)).fetchone()["c"]
            ags = conn.execute("SELECT COUNT(*) as c FROM agents a WHERE a.customer_name=?", (cn,)).fetchone()["c"]
            pages = conn.execute("""
                SELECT COALESCE(SUM(dc.counter_value), 0) as t
                FROM device_counters dc JOIN devices d ON d.id=dc.device_id JOIN agents a ON a.id=d.agent_id
                WHERE a.customer_name=? AND dc.counter_name LIKE '%Total%'
            """, (cn,)).fetchone()["t"]
            contract = conn.execute("SELECT cost_per_copy, monthly_cost, included_pages FROM contracts WHERE customer_name=? AND active=1 LIMIT 1", (cn,)).fetchone()
            cpc = contract["cost_per_copy"] if contract else 0
            mb = contract["monthly_cost"] if contract else 0
            inc = contract["included_pages"] if contract else 0
            over = max(0, pages - inc)
            writer.writerow([cn, devs, ags, pages, cpc, mb, inc, over, over * cpc, mb + over * cpc])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=custos.csv"},
    )
