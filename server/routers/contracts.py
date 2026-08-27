from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_role
from server.database import get_db

router = APIRouter(prefix="/contracts", tags=["contracts"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_role("admin", "technician")
async def contract_list(request: Request):
    user = request.state.user
    with get_db() as conn:
        contracts = conn.execute("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM contract_agents ca WHERE ca.contract_id = c.id) as agent_count
            FROM contracts c
            ORDER BY c.customer_name, c.name
        """).fetchall()

    return templates.TemplateResponse(request, "contracts/list.html", {
        "user": user,
        "contracts": contracts,
    })


@router.get("/new")
@require_role("admin")
async def contract_new_form(request: Request):
    user = request.state.user
    with get_db() as conn:
        agents = conn.execute("SELECT id, name, customer_name FROM agents ORDER BY name").fetchall()
    return templates.TemplateResponse(request, "contracts/form.html", {
        "user": user,
        "contract": None,
        "agents": agents,
        "selected_agents": [],
    })


@router.post("/new")
@require_role("admin")
async def contract_new_submit(
    request: Request,
    name: str = Form(...),
    customer_name: str = Form(...),
    cost_per_copy: float = Form(0.0),
    monthly_cost: float = Form(0.0),
    included_pages: int = Form(0),
    start_date: str = Form(""),
    end_date: str = Form(""),
    sla_hours: int = Form(24),
    notes: str = Form(""),
    agent_ids: list[int] = Form([]),
):
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO contracts (name, customer_name, cost_per_copy, monthly_cost,
               included_pages, start_date, end_date, sla_hours, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, customer_name, cost_per_copy, monthly_cost,
             included_pages, start_date or None, end_date or None, sla_hours, notes),
        )
        contract_id = cursor.lastrowid
        for agent_id in agent_ids:
            conn.execute(
                "INSERT INTO contract_agents (contract_id, agent_id) VALUES (?, ?)",
                (contract_id, agent_id),
            )
    return RedirectResponse("/contracts/", status_code=303)


@router.get("/{contract_id}")
@require_role("admin", "technician")
async def contract_detail(request: Request, contract_id: int):
    user = request.state.user
    with get_db() as conn:
        contract = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
        if not contract:
            raise HTTPException(status_code=404)

        linked_agents = conn.execute("""
            SELECT a.*, d.ip, d.model, d.manufacturer
            FROM contract_agents ca
            JOIN agents a ON a.id = ca.agent_id
            LEFT JOIN devices d ON d.agent_id = a.id
            WHERE ca.contract_id = ?
        """, (contract_id,)).fetchall()

        total_devices = conn.execute("""
            SELECT COUNT(*) as c FROM devices d
            JOIN contract_agents ca ON ca.agent_id = d.agent_id
            WHERE ca.contract_id = ?
        """, (contract_id,)).fetchone()["c"]

        total_pages_printed = 0
        if linked_agents:
            agent_ids = [a["id"] for a in linked_agents]
            placeholders = ",".join("?" * len(agent_ids))
            total_pages_printed = conn.execute(f"""
                SELECT COALESCE(SUM(dc.counter_value), 0) as total
                FROM device_counters dc
                JOIN devices d ON d.id = dc.device_id
                WHERE d.agent_id IN ({placeholders})
                AND dc.counter_name LIKE '%Total%'
            """, agent_ids).fetchone()["total"]

    return templates.TemplateResponse(request, "contracts/detail.html", {
        "user": user,
        "contract": contract,
        "linked_agents": linked_agents,
        "total_devices": total_devices,
        "total_pages_printed": total_pages_printed,
    })


@router.get("/{contract_id}/edit")
@require_role("admin")
async def contract_edit_form(request: Request, contract_id: int):
    user = request.state.user
    with get_db() as conn:
        contract = conn.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
        if not contract:
            raise HTTPException(status_code=404)
        agents = conn.execute("SELECT id, name, customer_name FROM agents ORDER BY name").fetchall()
        selected = conn.execute(
            "SELECT agent_id FROM contract_agents WHERE contract_id=?", (contract_id,)
        ).fetchall()
        selected_agents = [r["agent_id"] for r in selected]

    return templates.TemplateResponse(request, "contracts/form.html", {
        "user": user,
        "contract": contract,
        "agents": agents,
        "selected_agents": selected_agents,
    })


@router.post("/{contract_id}/edit")
@require_role("admin")
async def contract_edit_submit(
    request: Request,
    contract_id: int,
    name: str = Form(...),
    customer_name: str = Form(...),
    cost_per_copy: float = Form(0.0),
    monthly_cost: float = Form(0.0),
    included_pages: int = Form(0),
    start_date: str = Form(""),
    end_date: str = Form(""),
    sla_hours: int = Form(24),
    notes: str = Form(""),
    active: int = Form(1),
    agent_ids: list[int] = Form([]),
):
    with get_db() as conn:
        conn.execute(
            """UPDATE contracts SET name=?, customer_name=?, cost_per_copy=?, monthly_cost=?,
               included_pages=?, start_date=?, end_date=?, sla_hours=?, notes=?, active=?,
               updated_at=datetime('now') WHERE id=?""",
            (name, customer_name, cost_per_copy, monthly_cost,
             included_pages, start_date or None, end_date or None, sla_hours, notes, active, contract_id),
        )
        conn.execute("DELETE FROM contract_agents WHERE contract_id=?", (contract_id,))
        for agent_id in agent_ids:
            conn.execute(
                "INSERT INTO contract_agents (contract_id, agent_id) VALUES (?, ?)",
                (contract_id, agent_id),
            )
    return RedirectResponse(f"/contracts/{contract_id}", status_code=303)


@router.post("/{contract_id}/delete")
@require_role("admin")
async def contract_delete(request: Request, contract_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM contract_agents WHERE contract_id=?", (contract_id,))
        conn.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
    return RedirectResponse("/contracts/", status_code=303)
