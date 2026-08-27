from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_role
from server.database import get_db

router = APIRouter(prefix="/groups", tags=["groups"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_role("admin", "technician")
async def group_list(request: Request):
    user = request.state.user
    with get_db() as conn:
        groups = conn.execute("""
            SELECT dg.*,
                   (SELECT COUNT(*) FROM device_group_members dgm WHERE dgm.group_id = dg.id) as device_count
            FROM device_groups dg
            ORDER BY dg.name
        """).fetchall()

    return templates.TemplateResponse(request, "groups/list.html", {
        "user": user,
        "groups": groups,
    })


@router.get("/new")
@require_role("admin")
async def group_new_form(request: Request):
    user = request.state.user
    with get_db() as conn:
        devices = conn.execute("SELECT id, ip, manufacturer, model FROM devices ORDER BY ip").fetchall()
    return templates.TemplateResponse(request, "groups/form.html", {
        "user": user,
        "group": None,
        "devices": devices,
        "selected_devices": [],
    })


@router.post("/new")
@require_role("admin")
async def group_new_submit(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#0d6efd"),
    device_ids: list[int] = Form([]),
):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO device_groups (name, description, color) VALUES (?, ?, ?)",
            (name, description, color),
        )
        group_id = cursor.lastrowid
        for dev_id in device_ids:
            conn.execute(
                "INSERT INTO device_group_members (group_id, device_id) VALUES (?, ?)",
                (group_id, dev_id),
            )
    return RedirectResponse("/groups/", status_code=303)


@router.get("/{group_id}")
@require_role("admin", "technician")
async def group_detail(request: Request, group_id: int):
    user = request.state.user
    with get_db() as conn:
        group = conn.execute("SELECT * FROM device_groups WHERE id=?", (group_id,)).fetchone()
        if not group:
            raise HTTPException(status_code=404)
        members = conn.execute("""
            SELECT d.* FROM device_group_members dgm
            JOIN devices d ON d.id = dgm.device_id
            WHERE dgm.group_id = ?
            ORDER BY d.ip
        """, (group_id,)).fetchall()

    return templates.TemplateResponse(request, "groups/detail.html", {
        "user": user,
        "group": group,
        "members": members,
    })


@router.get("/{group_id}/edit")
@require_role("admin")
async def group_edit_form(request: Request, group_id: int):
    user = request.state.user
    with get_db() as conn:
        group = conn.execute("SELECT * FROM device_groups WHERE id=?", (group_id,)).fetchone()
        if not group:
            raise HTTPException(status_code=404)
        devices = conn.execute("SELECT id, ip, manufacturer, model FROM devices ORDER BY ip").fetchall()
        selected = conn.execute(
            "SELECT device_id FROM device_group_members WHERE group_id=?", (group_id,)
        ).fetchall()
        selected_devices = [r["device_id"] for r in selected]

    return templates.TemplateResponse(request, "groups/form.html", {
        "user": user,
        "group": group,
        "devices": devices,
        "selected_devices": selected_devices,
    })


@router.post("/{group_id}/edit")
@require_role("admin")
async def group_edit_submit(
    request: Request,
    group_id: int,
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#0d6efd"),
    device_ids: list[int] = Form([]),
):
    with get_db() as conn:
        conn.execute(
            "UPDATE device_groups SET name=?, description=?, color=?, updated_at=datetime('now') WHERE id=?",
            (name, description, color, group_id),
        )
        conn.execute("DELETE FROM device_group_members WHERE group_id=?", (group_id,))
        for dev_id in device_ids:
            conn.execute(
                "INSERT INTO device_group_members (group_id, device_id) VALUES (?, ?)",
                (group_id, dev_id),
            )
    return RedirectResponse(f"/groups/{group_id}", status_code=303)


@router.post("/{group_id}/delete")
@require_role("admin")
async def group_delete(request: Request, group_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM device_group_members WHERE group_id=?", (group_id,))
        conn.execute("DELETE FROM device_groups WHERE id=?", (group_id,))
    return RedirectResponse("/groups/", status_code=303)
