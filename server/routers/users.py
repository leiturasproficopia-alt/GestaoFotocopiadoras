from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR, ROLES
from server.auth import require_role, hash_password, verify_password
from server.database import get_db

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_role("admin")
async def user_list(request: Request):
    user = request.state.user
    with get_db() as conn:
        users = conn.execute(
            "SELECT id, username, name, email, role, active, created_at FROM users ORDER BY username"
        ).fetchall()

    return templates.TemplateResponse(request, "users/list.html", {
        "user": user,
        "users": users,
        "roles": ROLES,
    })


@router.get("/new")
@require_role("admin")
async def user_new_form(request: Request):
    user = request.state.user
    return templates.TemplateResponse(request, "users/form.html", {
        "user": user,
        "edit_user": None,
        "roles": ROLES,
    })


@router.post("/new")
@require_role("admin")
async def user_new_submit(
    request: Request,
    username: str = Form(...),
    name: str = Form(...),
    email: str = Form(""),
    role: str = Form("viewer"),
    password: str = Form(...),
):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="Role invalido")
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, name, email, role) VALUES (?, ?, ?, ?, ?)",
                (username, hash_password(password), name, email, role),
            )
        except Exception:
            return templates.TemplateResponse(
                request,
                "users/form.html",
                {"user": request.state.user, "edit_user": None, "roles": ROLES, "error": "Username ja existe"},
                status_code=400,
            )
    return RedirectResponse("/users/", status_code=303)


@router.get("/{user_id}/edit")
@require_role("admin")
async def user_edit_form(request: Request, user_id: int):
    user = request.state.user
    with get_db() as conn:
        edit_user = conn.execute(
            "SELECT id, username, name, email, role, active FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    if not edit_user:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "users/form.html", {
        "user": user,
        "edit_user": edit_user,
        "roles": ROLES,
    })


@router.post("/{user_id}/edit")
@require_role("admin")
async def user_edit_submit(
    request: Request,
    user_id: int,
    name: str = Form(...),
    email: str = Form(""),
    role: str = Form("viewer"),
    active: int = Form(1),
    password: str = Form(""),
):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="Role invalido")
    with get_db() as conn:
        if password:
            conn.execute(
                "UPDATE users SET name=?, email=?, role=?, active=?, password_hash=?, updated_at=datetime('now') WHERE id=?",
                (name, email, role, active, hash_password(password), user_id),
            )
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        else:
            conn.execute(
                "UPDATE users SET name=?, email=?, role=?, active=?, updated_at=datetime('now') WHERE id=?",
                (name, email, role, active, user_id),
            )
    return RedirectResponse("/users/", status_code=303)


@router.post("/{user_id}/delete")
@require_role("admin")
async def user_delete(request: Request, user_id: int):
    current_user = request.state.user
    if current_user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Nao pode eliminar a sua propria conta")
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return RedirectResponse("/users/", status_code=303)
