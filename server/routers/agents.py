from __future__ import annotations

import json
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from server.config import BASE_DIR
from server.auth import require_role
from server.database import get_db

router = APIRouter(prefix="/agents", tags=["agents"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
AGENT_TEMPLATE = BASE_DIR / "agent_standalone.py"


@router.get("/")
@require_role("admin", "technician")
async def agent_list(request: Request):
    user = request.state.user
    with get_db() as conn:
        agents = conn.execute("""
            SELECT a.*,
                   (SELECT COUNT(*) FROM devices WHERE agent_id = a.id) as device_count,
                   (SELECT COUNT(*) FROM devices WHERE agent_id = a.id AND online = 1) as online_count
            FROM agents a
            ORDER BY a.customer_name, a.name
        """).fetchall()

    return templates.TemplateResponse(request, "agents/list.html", {
        "user": user,
        "agents": agents,
    })


@router.get("/new")
@require_role("admin")
async def agent_new_form(request: Request):
    user = request.state.user
    return templates.TemplateResponse(request, "agents/form.html", {
        "user": user,
        "agent": None,
        "networks": [],
    })


@router.post("/new")
@require_role("admin")
async def agent_new_submit(
    request: Request,
    name: str = Form(...),
    customer_name: str = Form(""),
    discovery_interval: int = Form(4),
    discovery_unit: str = Form("hours"),
    counters_interval: int = Form(4),
    counters_unit: str = Form("hours"),
    supplies_interval: int = Form(1),
    supplies_unit: str = Form("hours"),
    alerts_interval: int = Form(60),
    alerts_unit: str = Form("minutes"),
    attributes_interval: int = Form(12),
    attributes_unit: str = Form("hours"),
    network_ip: list[str] = Form([]),
    network_hostname: list[str] = Form([]),
):
    new_token = secrets.token_hex(32)
    agent_uuid = uuid.uuid4().hex
    with get_db() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO agents (agent_id, name, customer_name, api_token,
                    discovery_interval, discovery_unit,
                    counters_interval, counters_unit,
                    supplies_interval, supplies_unit,
                    alerts_interval, alerts_unit,
                    attributes_interval, attributes_unit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_uuid, name, customer_name, new_token,
                 discovery_interval, discovery_unit,
                 counters_interval, counters_unit,
                 supplies_interval, supplies_unit,
                 alerts_interval, alerts_unit,
                 attributes_interval, attributes_unit),
            )
            agent_db_id = cursor.lastrowid
            _save_networks(conn, agent_db_id, network_ip, network_hostname)
        except Exception:
            raise HTTPException(status_code=400, detail="Erro ao criar agente")
    return RedirectResponse(f"/agents/{agent_db_id}/edit?new_token=1", status_code=303)


@router.get("/{agent_id}/edit")
@require_role("admin")
async def agent_edit_form(request: Request, agent_id: int, new_token: str = Query(None)):
    user = request.state.user
    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        networks = conn.execute(
            "SELECT * FROM agent_networks WHERE agent_id=? ORDER BY ip_address",
            (agent_id,),
        ).fetchall()
    if not agent:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "agents/form.html", {
        "user": user,
        "agent": agent,
        "networks": networks,
        "show_token": new_token == "1",
    })


@router.post("/{agent_id}/edit")
@require_role("admin")
async def agent_edit_submit(
    request: Request,
    agent_id: int,
    name: str = Form(...),
    customer_name: str = Form(""),
    active: int = Form(1),
    discovery_interval: int = Form(4),
    discovery_unit: str = Form("hours"),
    counters_interval: int = Form(4),
    counters_unit: str = Form("hours"),
    supplies_interval: int = Form(1),
    supplies_unit: str = Form("hours"),
    alerts_interval: int = Form(60),
    alerts_unit: str = Form("minutes"),
    attributes_interval: int = Form(12),
    attributes_unit: str = Form("hours"),
    network_ip: list[str] = Form([]),
    network_hostname: list[str] = Form([]),
):
    with get_db() as conn:
        conn.execute(
            """UPDATE agents SET name=?, customer_name=?, active=?,
                discovery_interval=?, discovery_unit=?,
                counters_interval=?, counters_unit=?,
                supplies_interval=?, supplies_unit=?,
                alerts_interval=?, alerts_unit=?,
                attributes_interval=?, attributes_unit=?,
                updated_at=datetime('now')
            WHERE id=?""",
            (name, customer_name, active,
             discovery_interval, discovery_unit,
             counters_interval, counters_unit,
             supplies_interval, supplies_unit,
             alerts_interval, alerts_unit,
             attributes_interval, attributes_unit,
             agent_id),
        )
        conn.execute("DELETE FROM agent_networks WHERE agent_id=?", (agent_id,))
        _save_networks(conn, agent_id, network_ip, network_hostname)
    return RedirectResponse("/agents/", status_code=303)


@router.post("/{agent_id}/delete")
@require_role("admin")
async def agent_delete(request: Request, agent_id: int):
    with get_db() as conn:
        device_ids = [r["id"] for r in conn.execute("SELECT id FROM devices WHERE agent_id=?", (agent_id,)).fetchall()]
        if device_ids:
            placeholders = ",".join("?" * len(device_ids))
            conn.execute(f"DELETE FROM device_counters WHERE device_id IN ({placeholders})", device_ids)
            conn.execute(f"DELETE FROM device_consumables WHERE device_id IN ({placeholders})", device_ids)
            conn.execute(f"DELETE FROM device_errors WHERE device_id IN ({placeholders})", device_ids)
            conn.execute(f"DELETE FROM device_status_history WHERE device_id IN ({placeholders})", device_ids)
            conn.execute(f"DELETE FROM devices WHERE id IN ({placeholders})", device_ids)
        conn.execute("DELETE FROM agent_networks WHERE agent_id=?", (agent_id,))
        conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    return RedirectResponse("/agents/", status_code=303)


@router.post("/{agent_id}/regenerate-token")
@require_role("admin")
async def agent_regenerate_token(request: Request, agent_id: int):
    new_token = secrets.token_hex(32)
    with get_db() as conn:
        conn.execute(
            "UPDATE agents SET api_token=?, updated_at=datetime('now') WHERE id=?",
            (new_token, agent_id),
        )
    return RedirectResponse(f"/agents/{agent_id}/edit?new_token=1", status_code=303)


@router.get("/{agent_id}/config")
@require_role("admin")
async def agent_download_config(request: Request, agent_id: int):
    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        networks = conn.execute(
            "SELECT ip_address FROM agent_networks WHERE agent_id=?",
            (agent_id,),
        ).fetchall()

    if not agent:
        raise HTTPException(status_code=404)

    def _to_seconds(interval: int, unit: str) -> int:
        if unit == "minutes":
            return interval * 60
        return interval * 3600

    config = {
        "agent": {
            "id": agent["agent_id"],
            "name": agent["name"],
            "scan_interval_seconds": _to_seconds(agent["discovery_interval"], agent["discovery_unit"]),
            "sync_interval_seconds": _to_seconds(agent["counters_interval"], agent["counters_unit"]),
            "concurrency": 50,
        },
        "snmp": {
            "versions": ["v2c", "v1"],
            "communities": ["public"],
            "timeout_seconds": 1.5,
            "retries": 1,
            "port": 161,
        },
        "networks": [n["ip_address"] for n in networks] if networks else ["192.168.1.0/24"],
        "database": {"path": "data/printer_monitor.db"},
        "logging": {
            "level": "INFO",
            "file": "logs/agent.log",
            "max_bytes": 5242880,
            "backup_count": 3,
        },
        "api": {
            "enabled": True,
            "base_url": str(request.base_url).rstrip("/"),
            "agent_token": agent["api_token"],
            "verify_tls": False,
            "timeout_seconds": 15,
        },
        "intervals": {
            "discovery_seconds": _to_seconds(agent["discovery_interval"], agent["discovery_unit"]),
            "counters_seconds": _to_seconds(agent["counters_interval"], agent["counters_unit"]),
            "supplies_seconds": _to_seconds(agent["supplies_interval"], agent["supplies_unit"]),
            "alerts_seconds": _to_seconds(agent["alerts_interval"], agent["alerts_unit"]),
            "attributes_seconds": _to_seconds(agent["attributes_interval"], agent["attributes_unit"]),
        },
    }

    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=config,
        headers={"Content-Disposition": f'attachment; filename="config_{agent["name"]}.json"'},
    )


@router.get("/{agent_id}/exe")
@require_role("admin")
async def agent_download_exe(request: Request, agent_id: int, server_url: str | None = None):
    if sys.platform != "win32":
        raise HTTPException(
            status_code=400,
            detail="Geracao de EXE so disponivel no Windows. Use Linux ou Mac installer.",
        )

    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        networks = conn.execute(
            "SELECT ip_address FROM agent_networks WHERE agent_id=?",
            (agent_id,),
        ).fetchall()

    if not agent:
        raise HTTPException(status_code=404)

    def _to_seconds(interval: int, unit: str) -> int:
        if unit == "minutes":
            return interval * 60
        return interval * 3600

    network_list = [n["ip_address"] for n in networks] if networks else ["192.168.1.0/24"]
    if server_url:
        server_url = server_url.rstrip("/")
    else:
        server_url = str(request.base_url).rstrip("/")

    template_code = AGENT_TEMPLATE.read_text(encoding="utf-8")

    replacements = {
        "{{AGENT_ID}}": agent["agent_id"],
        "{{AGENT_NAME}}": agent["name"],
        "{{SERVER_URL}}": server_url,
        "{{API_TOKEN}}": agent["api_token"],
        "{{NETWORKS}}": json.dumps(network_list),
        "{{DISCOVERY_SECONDS}}": str(_to_seconds(agent["discovery_interval"], agent["discovery_unit"])),
        "{{COUNTERS_SECONDS}}": str(_to_seconds(agent["counters_interval"], agent["counters_unit"])),
        "{{SUPPLIES_SECONDS}}": str(_to_seconds(agent["supplies_interval"], agent["supplies_unit"])),
        "{{ALERTS_SECONDS}}": str(_to_seconds(agent["alerts_interval"], agent["alerts_unit"])),
        "{{ATTRIBUTES_SECONDS}}": str(_to_seconds(agent["attributes_interval"], agent["attributes_unit"])),
    }

    for placeholder, value in replacements.items():
        template_code = template_code.replace(placeholder, value)

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        script_path = tmp_dir / "agent.py"
        script_path.write_text(template_code, encoding="utf-8")

        version_info = BASE_DIR / "version_info.txt"
        if version_info.exists():
            (tmp_dir / "version_info.txt").write_text(
                version_info.read_text(encoding="utf-8"), encoding="utf-8"
            )

        exe_name = f"Agente_{agent['name'].replace(' ', '_')}"

        pyinstaller_args = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--console",
            "--name", exe_name,
            "--distpath", str(tmp_dir),
            "--workpath", str(tmp_dir / "build"),
            "--specpath", str(tmp_dir),
            "--hidden-import", "pystray",
            "--hidden-import", "PIL",
            "--hidden-import", "PIL.Image",
            "--hidden-import", "PIL.ImageDraw",
            "--hidden-import", "win32serviceutil",
            "--hidden-import", "win32service",
            "--hidden-import", "win32event",
            "--hidden-import", "win32timezone",
            "--hidden-import", "servicemanager",
            "--hidden-import", "pysnmp.hlapi.v3arch.asyncio",
            "--clean",
            "--log-level", "ERROR",
        ]

        if version_info.exists():
            pyinstaller_args.extend(["--version-file", str(tmp_dir / "version_info.txt")])

        pyinstaller_args.append(str(script_path))

        result = subprocess.run(
            pyinstaller_args,
            capture_output=True,
            text=True,
            timeout=180,
        )

        exe_path = tmp_dir / f"{exe_name}.exe"
        if not exe_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao gerar EXE: {result.stderr[:500]}",
            )

        return FileResponse(
            path=str(exe_path),
            filename=f"{exe_name}.exe",
            media_type="application/octet-stream",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Timeout ao gerar EXE.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar EXE: {exc}")


def _build_agent_code(agent, networks, server_url):
    def _to_seconds(interval, unit):
        if unit == "minutes":
            return interval * 60
        return interval * 3600

    network_list = [n["ip_address"] for n in networks] if networks else ["192.168.1.0/24"]
    template_code = AGENT_TEMPLATE.read_text(encoding="utf-8")

    replacements = {
        "{{AGENT_ID}}": agent["agent_id"],
        "{{AGENT_NAME}}": agent["name"],
        "{{SERVER_URL}}": server_url,
        "{{API_TOKEN}}": agent["api_token"],
        "{{NETWORKS}}": json.dumps(network_list),
        "{{DISCOVERY_SECONDS}}": str(_to_seconds(agent["discovery_interval"], agent["discovery_unit"])),
        "{{COUNTERS_SECONDS}}": str(_to_seconds(agent["counters_interval"], agent["counters_unit"])),
        "{{SUPPLIES_SECONDS}}": str(_to_seconds(agent["supplies_interval"], agent["supplies_unit"])),
        "{{ALERTS_SECONDS}}": str(_to_seconds(agent["alerts_interval"], agent["alerts_unit"])),
        "{{ATTRIBUTES_SECONDS}}": str(_to_seconds(agent["attributes_interval"], agent["attributes_unit"])),
    }

    for placeholder, value in replacements.items():
        template_code = template_code.replace(placeholder, value)

    return template_code


def _get_agent_networks(conn, agent_id):
    return conn.execute(
        "SELECT ip_address FROM agent_networks WHERE agent_id=?",
        (agent_id,),
    ).fetchall()


def _get_agent_context(agent_id: int):
    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not agent:
            raise HTTPException(status_code=404)
        networks = _get_agent_networks(conn, agent_id)
    return agent, networks


SERVICE_AGENT_LINUX = "fotocopiadora-agent"
SERVICE_AGENT_MAC = "com.fotocopiadora.agent"


@router.get("/{agent_id}/install-linux")
@require_role("admin")
async def agent_download_linux(request: Request, agent_id: int, server_url: str | None = None):
    agent, networks = _get_agent_context(agent_id)
    if server_url:
        server_url = server_url.rstrip("/")
    else:
        server_url = str(request.base_url).rstrip("/")
    agent_code = _build_agent_code(agent, networks, server_url)
    agent_name = agent["name"].replace(" ", "_").lower()

    agent_code_escaped = agent_code.replace("\\", "\\\\").replace("'", "'\\''")

    install_script = f"""#!/bin/bash
set -e

AGENT_NAME="{agent_name}"
AGENT_DIR="/opt/fotocopiadora-agent"
SERVICE_NAME="fotocopiadora-agent"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "  Agente Fotocopiadoras - Instalador"
echo "========================================="
echo ""

# Verificar/instalar Python
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[*] Python nao encontrado. A instalar..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
    elif command -v yum &>/dev/null; then
        sudo yum install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python python-pip
    else
        echo "ERRO: Nao foi possivel instalar Python automaticamente."
        echo "Instale manualmente: sudo apt install python3 python3-pip"
        exit 1
    fi
    PYTHON=$(command -v python3 || command -v python)
fi

echo "[+] Python encontrado: $PYTHON ($($PYTHON --version 2>&1))"

# Instalar dependencias
echo "[*] A instalar dependencias..."
$PYTHON -m pip install --quiet --break-system-packages pysnmp 2>/dev/null || \\
$PYTHON -m pip install --quiet pysnmp 2>/dev/null || true

# Criar diretorio
echo "[*] A instalar agente em $AGENT_DIR ..."
sudo mkdir -p "$AGENT_DIR/logs"

# Extrair agent.py deste script
sudo tee "$AGENT_DIR/agent.py" > /dev/null << 'AGENTEOF'
{agent_code}
AGENTEOF
sudo chmod +x "$AGENT_DIR/agent.py"

# Criar servico systemd
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << SVCEOF
[Unit]
Description=Agente de Monitoramento de Fotocopiadoras
After=network.target

[Service]
Type=simple
ExecStart=$PYTHON $AGENT_DIR/agent.py
Restart=always
RestartSec=10
WorkingDirectory=$AGENT_DIR

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME 2>/dev/null
sudo systemctl restart $SERVICE_NAME

echo ""
echo "========================================="
echo "  Agente instalado com sucesso!"
echo "========================================="
echo ""
echo "Estado:    sudo systemctl status $SERVICE_NAME"
echo "Reiniciar: sudo systemctl restart $SERVICE_NAME"
echo "Parar:     sudo systemctl stop $SERVICE_NAME"
echo "Logs:      sudo journalctl -u $SERVICE_NAME -f"
echo "Remover:   sudo systemctl stop $SERVICE_NAME && sudo systemctl disable $SERVICE_NAME && sudo rm /etc/systemd/system/$SERVICE_NAME.service && sudo rm -rf $AGENT_DIR"
"""

    return StreamingResponse(
        iter([install_script.encode("utf-8")]),
        media_type="application/x-sh",
        headers={"Content-Disposition": f"attachment; filename={agent_name}-linux-install.sh"},
    )


@router.get("/{agent_id}/install-mac")
@require_role("admin")
async def agent_download_mac(request: Request, agent_id: int, server_url: str | None = None):
    agent, networks = _get_agent_context(agent_id)
    if server_url:
        server_url = server_url.rstrip("/")
    else:
        server_url = str(request.base_url).rstrip("/")
    agent_code = _build_agent_code(agent, networks, server_url)
    agent_name = agent["name"].replace(" ", "_").lower()

    install_script = f"""#!/bin/bash
set -e

AGENT_NAME="{agent_name}"
AGENT_DIR="$HOME/Library/Application Support/FotocopiadoraAgent"
PLIST_PATH="$HOME/Library/LaunchAgents/com.fotocopiadora.agent.plist"
LOG_DIR="$AGENT_DIR/logs"

echo "========================================="
echo "  Agente Fotocopiadoras - Instalador"
echo "========================================="
echo ""

# Verificar/instalar Python
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[*] Python nao encontrado."
    if command -v brew &>/dev/null; then
        echo "[*] A instalar via Homebrew..."
        brew install python3
    else
        echo "ERRO: Instale Python3 manualmente:"
        echo "  brew install python3"
        echo "  ou descarregue de: https://www.python.org/downloads/"
        exit 1
    fi
    PYTHON=$(command -v python3 || command -v python)
fi

echo "[+] Python encontrado: $PYTHON ($($PYTHON --version 2>&1))"

# Instalar dependencias
echo "[*] A instalar dependencias..."
$PYTHON -m pip install --quiet pysnmp 2>/dev/null || true

# Criar diretorio
echo "[*] A instalar agente em $AGENT_DIR ..."
mkdir -p "$LOG_DIR"

# Extrair agent.py
cat > "$AGENT_DIR/agent.py" << 'AGENTEOF'
{agent_code}
AGENTEOF
chmod +x "$AGENT_DIR/agent.py"

# Criar launchd plist
mkdir -p "$(dirname "$PLIST_PATH")"
cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.fotocopiadora.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$AGENT_DIR/agent.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$AGENT_DIR</string>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/agent.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "========================================="
echo "  Agente instalado com sucesso!"
echo "========================================="
echo ""
echo "Estado:    launchctl list | grep fotocopiadora"
echo "Reiniciar: launchctl stop com.fotocopiadora.agent && launchctl start com.fotocopiadora.agent"
echo "Parar:     launchctl stop com.fotocopiadora.agent"
echo "Logs:      tail -f $LOG_DIR/agent.log"
echo "Remover:   launchctl unload $PLIST_PATH && rm -rf $AGENT_DIR $PLIST_PATH"
"""

    return StreamingResponse(
        iter([install_script.encode("utf-8")]),
        media_type="application/x-sh",
        headers={"Content-Disposition": f"attachment; filename={agent_name}-mac-install.sh"},
    )


def _save_networks(conn, agent_id: int, ips: list[str], hostnames: list[str]):
    seen = set()
    for i, ip in enumerate(ips):
        ip = ip.strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        hostname = hostnames[i].strip() if i < len(hostnames) else ""
        try:
            conn.execute(
                "INSERT INTO agent_networks (agent_id, ip_address, hostname) VALUES (?, ?, ?)",
                (agent_id, ip, hostname),
            )
        except Exception:
            pass
