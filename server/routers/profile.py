from __future__ import annotations

import json

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR, SESSION_COOKIE_NAME
from server.auth import require_login, hash_password, verify_password
from server.database import get_db
from server.audit import log_audit

router = APIRouter(prefix="/profile", tags=["profile"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/")
@require_login
async def profile_page(request: Request):
    user = request.state.user
    with get_db() as conn:
        full_user = conn.execute(
            "SELECT id, username, name, email, role, created_at FROM users WHERE id=?",
            (user["id"],),
        ).fetchone()
        sessions = conn.execute(
            "SELECT id, created_at, expires_at, ip_address, user_agent FROM sessions WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
        prefs = conn.execute(
            "SELECT * FROM user_preferences WHERE user_id=?",
            (user["id"],),
        ).fetchone()
        if not prefs:
            conn.execute(
                "INSERT INTO user_preferences (user_id) VALUES (?)",
                (user["id"],),
            )
            conn.commit()
            prefs = conn.execute(
                "SELECT * FROM user_preferences WHERE user_id=?",
                (user["id"],),
            ).fetchone()

    return templates.TemplateResponse(request, "profile/page.html", {
        "user": user,
        "full_user": full_user,
        "sessions": sessions,
        "prefs": prefs,
    })


@router.post("/update")
@require_login
async def profile_update(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
):
    user = request.state.user
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET name=?, email=?, updated_at=datetime('now') WHERE id=?",
            (name, email, user["id"]),
        )
        log_audit(user["id"], user["username"], "update", "user", user["id"],
                  new_value=json.dumps({"name": name, "email": email}),
                  ip_address=request.client.host if request.client else "")
    return RedirectResponse("/profile/", status_code=303)


@router.post("/change-password")
@require_login
async def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    user = request.state.user
    with get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id=?",
            (user["id"],),
        ).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            return templates.TemplateResponse(request, "profile/page.html", {
                "user": user,
                "full_user": user,
                "sessions": [],
                "prefs": {},
                "error": "Password atual incorreta",
            }, status_code=400)

        conn.execute(
            "UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE id=?",
            (hash_password(new_password), user["id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        log_audit(user["id"], user["username"], "change_password", "user", user["id"],
                  ip_address=request.client.host if request.client else "")

    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.post("/preferences")
@require_login
async def profile_update_preferences(
    request: Request,
    theme: str = Form("light"),
    notifications: int = Form(1),
    dashboard_refresh: int = Form(30),
):
    user = request.state.user
    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_preferences (user_id, theme, notifications, dashboard_refresh)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                theme=excluded.theme,
                notifications=excluded.notifications,
                dashboard_refresh=excluded.dashboard_refresh,
                updated_at=datetime('now')
        """, (user["id"], theme, notifications, dashboard_refresh))
    return RedirectResponse("/profile/", status_code=303)


@router.post("/sessions/{session_id}/revoke")
@require_login
async def profile_revoke_session(request: Request, session_id: int):
    user = request.state.user
    with get_db() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE id=? AND user_id=?",
            (session_id, user["id"]),
        )
    return RedirectResponse("/profile/", status_code=303)
