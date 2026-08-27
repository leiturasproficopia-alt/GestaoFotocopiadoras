from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.database import initialize_database
from server.migrations.runner import run_migrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("gestao")


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    run_migrations()
    _seed_admin_if_needed()
    yield


def _seed_admin_if_needed():
    from server.database import get_db
    from server.auth import hash_password
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, password_hash, name, role) VALUES (?, ?, ?, ?)",
                ("admin", hash_password("admin"), "Administrador", "admin"),
            )


app = FastAPI(
    title="Gestao de Fotocopiadoras",
    description="Plataforma de gestao de fotocopiadoras via SNMP",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

from server.routers import auth as auth_router
from server.routers import dashboard as dashboard_router
from server.routers import devices as devices_router
from server.routers import counters as counters_router
from server.routers import consumables as consumables_router
from server.routers import errors as errors_router
from server.routers import agents as agents_router
from server.routers import users as users_router
from server.routers import api_agent as api_agent_router
from server.routers import export as export_router
from server.routers import alerts as alerts_router
from server.routers import contracts as contracts_router
from server.routers import reports as reports_router
from server.routers import profile as profile_router
from server.routers import costs as costs_router
from server.routers import groups as groups_router
from server.routers import admin as admin_router

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(devices_router.router)
app.include_router(counters_router.router)
app.include_router(consumables_router.router)
app.include_router(errors_router.router)
app.include_router(agents_router.router)
app.include_router(users_router.router)
app.include_router(api_agent_router.router)
app.include_router(export_router.router)
app.include_router(alerts_router.router)
app.include_router(contracts_router.router)
app.include_router(reports_router.router)
app.include_router(profile_router.router)
app.include_router(costs_router.router)
app.include_router(groups_router.router)
app.include_router(admin_router.router)


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/health")
async def health_check():
    from server.database import get_db
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "database": "ok"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
