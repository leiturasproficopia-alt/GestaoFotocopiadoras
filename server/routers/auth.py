from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import verify_password, create_session, get_current_user
from server.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/login")
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, name, role, active FROM users WHERE username=?",
            (username,),
        ).fetchone()

    if not row or not verify_password(password, row["password_hash"]) or not row["active"]:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Credenciais invalidas"},
            status_code=401,
        )

    response = RedirectResponse("/dashboard", status_code=303)
    create_session(response, row["id"], row["username"])
    return response


@router.get("/logout")
async def logout(request: Request):
    from server.config import SESSION_COOKIE_NAME
    token = request.cookies.get(SESSION_COOKIE_NAME)
    response = RedirectResponse("/auth/login", status_code=303)
    if token:
        from server.auth import destroy_session
        destroy_session(response, token)
    return response
