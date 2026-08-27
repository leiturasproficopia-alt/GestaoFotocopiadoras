from __future__ import annotations

import json

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_role
from server.database import get_db
from server.backup import create_backup, list_backups, restore_backup, delete_backup
from server.audit import log_audit

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/backup")
@require_role("admin")
async def backup_page(request: Request):
    user = request.state.user
    backups = list_backups()
    return templates.TemplateResponse(request, "admin/backup.html", {
        "user": user,
        "backups": backups,
    })


@router.post("/backup/create")
@require_role("admin")
async def backup_create(request: Request):
    user = request.state.user
    path = create_backup()
    log_audit(user["id"], user["username"], "backup_create", "system",
              new_value=path.name, ip_address=request.client.host if request.client else "")
    return RedirectResponse("/admin/backup", status_code=303)


@router.get("/backup/download/{filename}")
@require_role("admin")
async def backup_download(filename: str):
    from server.backup import BACKUP_DIR
    path = BACKUP_DIR / filename
    if path.exists():
        return FileResponse(str(path), filename=filename, media_type="application/octet-stream")
    return RedirectResponse("/admin/backup", status_code=303)


@router.post("/backup/restore")
@require_role("admin")
async def backup_restore(request: Request):
    user = request.state.user
    form = await request.form()
    filename = form.get("filename", "")
    from server.backup import BACKUP_DIR
    path = BACKUP_DIR / filename
    if path.exists():
        restore_backup(path)
        log_audit(user["id"], user["username"], "backup_restore", "system",
                  new_value=filename, ip_address=request.client.host if request.client else "")
    return RedirectResponse("/admin/backup", status_code=303)


@router.post("/backup/upload")
@require_role("admin")
async def backup_upload(request: Request):
    user = request.state.user
    form = await request.form()
    file = form.get("file")
    if file and hasattr(file, "filename"):
        from server.backup import BACKUP_DIR
        content = await file.read()
        path = BACKUP_DIR / file.filename
        path.write_bytes(content)
        log_audit(user["id"], user["username"], "backup_upload", "system",
                  new_value=file.filename, ip_address=request.client.host if request.client else "")
    return RedirectResponse("/admin/backup", status_code=303)


@router.post("/backup/delete")
@require_role("admin")
async def backup_delete(request: Request):
    user = request.state.user
    form = await request.form()
    filename = form.get("filename", "")
    from server.backup import BACKUP_DIR
    path = BACKUP_DIR / filename
    delete_backup(path)
    log_audit(user["id"], user["username"], "backup_delete", "system",
              new_value=filename, ip_address=request.client.host if request.client else "")
    return RedirectResponse("/admin/backup", status_code=303)


@router.get("/audit")
@require_role("admin")
async def audit_log_page(request: Request, page: int = 1):
    user = request.state.user
    per_page = 50
    offset = (page - 1) * per_page
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"]
        logs = conn.execute("""
            SELECT * FROM audit_log
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset)).fetchall()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "admin/audit.html", {
        "user": user,
        "logs": logs,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    })
