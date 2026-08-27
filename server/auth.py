from __future__ import annotations

import functools
import hashlib
import os
from typing import Callable

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

from server.config import SESSION_COOKIE_NAME, SESSION_MAX_AGE, ROLES
from server.database import get_db


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return salt.hex() + ":" + h.hex()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        salt_hex, hash_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        h = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 100000)
        return h.hex() == hash_hex
    except Exception:
        return False


def create_session_token(user_id: int, username: str) -> str:
    import secrets
    return secrets.token_hex(32)


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, name, email, role FROM users WHERE active=1 AND id IN (SELECT user_id FROM sessions WHERE token=?)",
            (token,),
        ).fetchone()
        if row:
            return dict(row)
    return None


def create_session(response, user_id: int, username: str):
    from datetime import datetime, timezone
    token = create_session_token(user_id, username)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token, created_at) VALUES (?, ?, ?)",
            (user_id, token, now),
        )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def destroy_session(response, token: str):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    response.delete_cookie(SESSION_COOKIE_NAME)


def require_login(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/auth/login", status_code=303)
        request.state.user = user
        return await func(request, *args, **kwargs)
    return wrapper


def require_role(*allowed_roles: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = get_current_user(request)
            if not user:
                return RedirectResponse("/auth/login", status_code=303)
            if user["role"] not in allowed_roles:
                raise HTTPException(status_code=403, detail="Sem permissao")
            request.state.user = user
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
