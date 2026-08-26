"""
Agente Fotocopiadoras - Versao Standalone
Gerado automaticamente pelo servidor.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import sqlite3
import ssl
import sys
import time
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Configuracao Embebida (preenchida pelo servidor) ---
AGENT_CONFIG = {
    "agent_id": "{{AGENT_ID}}",
    "agent_name": "{{AGENT_NAME}}",
    "server_url": "{{SERVER_URL}}",
    "api_token": "{{API_TOKEN}}",
    "networks": {{NETWORKS}},
    "intervals": {
        "discovery": {{DISCOVERY_SECONDS}},
        "counters": {{COUNTERS_SECONDS}},
        "supplies": {{SUPPLIES_SECONDS}},
        "alerts": {{ALERTS_SECONDS}},
        "attributes": {{ATTRIBUTES_SECONDS}},
    },
    "snmp": {
        "communities": ["public"],
        "versions": ["v2c", "v1"],
        "port": 161,
        "timeout": 1.5,
        "retries": 1,
    },
}

SERVICE_NAME = "FotocopiadoraAgent"
DISPLAY_NAME = "Servico de Impressoras"

# --- Logging ---
LOG_DIR = Path(os.environ.get("APPDATA", ".")) / "FotocopiadoraAgent" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8"),
    ],
)
LOGGER = logging.getLogger("agent")

# --- SNMP ---
try:
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData, ContextData, ObjectIdentity, ObjectType,
        SnmpEngine, UdpTransportTarget, get_cmd, walk_cmd,
    )
    HAS_PYSNMP = True
except ImportError:
    HAS_PYSNMP = False


class SnmpClient:
    def __init__(self, ip, community="public", version="v2c", port=161, timeout=1.5, retries=1):
        self.ip = ip
        self.community = community
        self.version = version
        self.port = port
        self.timeout = timeout
        self.retries = retries

    async def get_many(self, oids):
        if not HAS_PYSNMP:
            return {}
        engine = SnmpEngine()
        try:
            community = CommunityData(self.community, mpModel=0 if self.version == "v1" else 1)
            transport = await UdpTransportTarget.create(
                (self.ip, self.port), timeout=self.timeout, retries=self.retries,
            )
            ei, es, ix, binds = await get_cmd(
                engine, community, transport, ContextData(),
                *[ObjectType(ObjectIdentity(oid)) for oid in oids],
            )
            if ei or es:
                return {}
            return {oid: bind[1] for oid, bind in zip(oids, binds)}
        except Exception:
            return {}
        finally:
            engine.close_dispatcher()

    async def walk(self, base_oid, max_rows=200):
        if not HAS_PYSNMP:
            return []
        engine = SnmpEngine()
        result = []
        try:
            community = CommunityData(self.community, mpModel=0 if self.version == "v1" else 1)
            transport = await UdpTransportTarget.create(
                (self.ip, self.port), timeout=self.timeout, retries=self.retries,
            )
            iterator = walk_cmd(
                engine, community, transport, ContextData(),
                ObjectType(ObjectIdentity(base_oid)),
                lexicographicMode=False,
            )
            async for ei, es, ix, binds in iterator:
                if ei or es:
                    break
                for bind in binds:
                    result.append((str(bind[0]), bind[1]))
                    if len(result) >= max_rows:
                        return result
            return result
        except Exception:
            return []
        finally:
            engine.close_dispatcher()


# --- OIDs ---
SYSTEM_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
}

PRINTER_OIDS = {
    "prtGeneralSerialNumber": "1.3.6.1.2.1.43.5.1.1.17.1",
    "prtMarkerLifeCount": "1.3.6.1.2.1.43.10.2.1.4.1.1",
    "prtMarkerPowerOnCount": "1.3.6.1.2.1.43.10.2.1.5.1.1",
    "prtMarkerSuppliesDescription": "1.3.6.1.2.1.43.11.1.1.6.1",
    "prtMarkerSuppliesMaxCapacity": "1.3.6.1.2.1.43.11.1.1.8.1",
    "prtMarkerSuppliesLevel": "1.3.6.1.2.1.43.11.1.1.9.1",
    "prtAlertCode": "1.3.6.1.2.1.43.18.1.1.8.1",
    "prtAlertDescription": "1.3.6.1.2.1.43.18.1.1.7.1",
}

VENDOR_COUNTER_OIDS = {
    "Ricoh": {
        "Total de Paginas": "1.3.6.1.4.1.367.3.2.1.2.19.1.0",
        "Total de Paginas Impressao": "1.3.6.1.4.1.367.3.2.1.2.19.2.0",
        "Total de Paginas Fax": "1.3.6.1.4.1.367.3.2.1.2.19.3.0",
        "Total de Paginas Copiadas": "1.3.6.1.4.1.367.3.2.1.2.19.4.0",
    },
    "Konica Minolta": {
        "Total de Paginas": "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.1.0",
        "Total de Paginas Duplex": "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.3.0",
        "Total de Scans": "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.5.0",
        "Total Copias Mono": "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.1",
        "Total Copias Color": "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.2.1",
        "Total Impressoes Mono": "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.2",
        "Total Impressoes Color": "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.2.2",
    },
    "Xerox": {
        "Total de Paginas": "1.3.6.1.4.1.253.8.53.13.2.1.6.1.0",
        "Total Impressoes": "1.3.6.1.4.1.253.8.53.13.2.1.6.1.16",
        "Total Copias": "1.3.6.1.4.1.253.8.53.13.2.1.6.1.15",
        "Total Scans": "1.3.6.1.4.1.253.8.53.13.2.1.6.1.18",
    },
    "Canon": {
        "Total de Paginas": "1.3.6.1.4.1.1602.1.11.1.3.1.4.100",
        "Total Impressoes": "1.3.6.1.4.1.1602.1.11.1.3.1.4.111",
        "Total Copias": "1.3.6.1.4.1.1602.1.11.1.3.1.4.110",
        "Total Scans": "1.3.6.1.4.1.1602.1.11.1.3.1.4.130",
    },
    "HP": {
        "Total de Paginas": "1.3.6.1.2.1.43.10.2.1.4.1.1",
    },
    "Kyocera": {
        "Total de Paginas": "1.3.6.1.4.1.1347.42.5.2.1.4.1",
        "Total Impressoes": "1.3.6.1.4.1.1347.42.5.2.1.4.1",
        "Total Copias": "1.3.6.1.4.1.1347.42.5.2.1.4.2",
        "Total Scans": "1.3.6.1.4.1.1347.42.5.2.1.4.3",
    },
    "Brother": {
        "Total de Paginas": "1.3.6.1.4.1.2435.2.3.9.4.2.1.5.5.1",
    },
    "Samsung": {
        "Total de Paginas": "1.3.6.1.4.1.236.11.1.8.1.1.1",
    },
    "Lexmark": {
        "Total de Paginas": "1.3.6.1.4.1.641.2.1.2.1.5.1",
    },
}


def py_value(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, (int, float, str, bool)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return str(value).strip()
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return str(value).strip()
        except Exception:
            return None


KNOWN_MANUFACTURERS = {
    "ricoh": "Ricoh", "lanier": "Ricoh", "savin": "Ricoh",
    "konica": "Konica Minolta", "minolta": "Konica Minolta",
    "xerox": "Xerox", "hp": "HP", "hewlett": "HP",
    "canon": "Canon", "epson": "Epson", "brother": "Brother",
    "kyocera": "Kyocera", "samsung": "Samsung", "lexmark": "Lexmark",
    "sharp": "Sharp", "oki": "OKI", "dezzle": "Dezzle",
}


def identify_manufacturer(descr, objid, name):
    text = f"{descr} {objid} {name}".lower()
    for key, mfg in KNOWN_MANUFACTURERS.items():
        if key in text:
            return mfg
    return "Desconhecido"


# --- Database ---
DB_PATH = Path(os.environ.get("APPDATA", ".")) / "FotocopiadoraAgent" / "agent.db"


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            ip TEXT PRIMARY KEY,
            manufacturer TEXT DEFAULT '',
            model TEXT DEFAULT '',
            serial_number TEXT DEFAULT '',
            sys_descr TEXT DEFAULT '',
            sys_object_id TEXT DEFAULT '',
            sys_name TEXT DEFAULT '',
            counters_json TEXT DEFAULT '{}',
            supplies_json TEXT DEFAULT '[]',
            alerts_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'unknown',
            last_seen TEXT
        );
    """)
    conn.close()


# --- API Client ---
def api_request(path, data=None, method="POST"):
    url = f"{AGENT_CONFIG['server_url']}{path}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AGENT_CONFIG['api_token']}",
    }
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            resp_body = exc.read().decode()
        except Exception:
            resp_body = ""
        LOGGER.error("API error %s: %s - %s", exc.code, exc.reason, resp_body[:500])
        return None
    except Exception as exc:
        LOGGER.error("API error: %s", exc)
        return None


# --- SNMP Collection ---
async def probe_device(ip):
    cfg = AGENT_CONFIG["snmp"]
    for version in cfg["versions"]:
        for community in cfg["communities"]:
            client = SnmpClient(ip, community, version, cfg["port"], cfg["timeout"], cfg["retries"])
            values = await client.get_many([
                SYSTEM_OIDS["sysDescr"],
                SYSTEM_OIDS["sysObjectID"],
                SYSTEM_OIDS["sysName"],
            ])
            descr = str(py_value(values.get(SYSTEM_OIDS["sysDescr"])) or "")
            objid = str(py_value(values.get(SYSTEM_OIDS["sysObjectID"])) or "")
            name = str(py_value(values.get(SYSTEM_OIDS["sysName"])) or "")
            if not descr and not objid:
                continue
            manufacturer = identify_manufacturer(descr, objid, name)
            return {
                "ip": ip,
                "manufacturer": manufacturer,
                "model": name or descr[:50],
                "sys_descr": descr,
                "sys_object_id": objid,
                "sys_name": name,
                "snmp_version": version,
                "community": community,
                "status": "online",
            }
    return None


async def collect_device(device):
    client = SnmpClient(device["ip"], device["community"], device["snmp_version"])
    values = await client.get_many([
        SYSTEM_OIDS["sysDescr"], SYSTEM_OIDS["sysObjectID"],
        SYSTEM_OIDS["sysContact"], SYSTEM_OIDS["sysName"],
        SYSTEM_OIDS["sysLocation"], PRINTER_OIDS["prtGeneralSerialNumber"],
    ])
    device["serial_number"] = str(py_value(values.get(PRINTER_OIDS["prtGeneralSerialNumber"])) or "")
    device["sys_contact"] = str(py_value(values.get(SYSTEM_OIDS["sysContact"])) or "")
    device["sys_location"] = str(py_value(values.get(SYSTEM_OIDS["sysLocation"])) or "")

    counters = {}

    manufacturer = device.get("manufacturer", "")
    vendor_oids = VENDOR_COUNTER_OIDS.get(manufacturer, {})
    if vendor_oids:
        oid_list = list(vendor_oids.values())
        oid_results = await client.get_many(oid_list)
        name_by_oid = {v: k for k, v in vendor_oids.items()}
        for oid_val, name_key in name_by_oid.items():
            val = py_value(oid_results.get(oid_val))
            if val is not None:
                counters[name_key] = val

    generic_oids = await client.get_many([
        PRINTER_OIDS["prtMarkerLifeCount"], PRINTER_OIDS["prtMarkerPowerOnCount"],
    ])
    life_val = py_value(generic_oids.get(PRINTER_OIDS["prtMarkerLifeCount"]))
    power_val = py_value(generic_oids.get(PRINTER_OIDS["prtMarkerPowerOnCount"]))
    if life_val is not None and "Total de Paginas" not in counters:
        counters["Total de Paginas"] = life_val
    if power_val is not None:
        counters["Ligacoes"] = power_val

    device["counters"] = counters

    supplies = []
    desc_vals = await client.walk(PRINTER_OIDS["prtMarkerSuppliesDescription"])
    max_vals = await client.walk(PRINTER_OIDS["prtMarkerSuppliesMaxCapacity"])
    level_vals = await client.walk(PRINTER_OIDS["prtMarkerSuppliesLevel"])
    desc_map = {str(k).split(".")[-1]: py_value(v) for k, v in desc_vals}
    max_map = {str(k).split(".")[-1]: py_value(v) for k, v in max_vals}
    level_map = {str(k).split(".")[-1]: py_value(v) for k, v in level_vals}
    for idx in desc_map:
        supplies.append({
            "description": desc_map.get(idx, ""),
            "max": max_map.get(idx),
            "level": level_map.get(idx),
        })
    device["supplies"] = supplies

    alerts = []
    code_vals = await client.walk(PRINTER_OIDS["prtAlertCode"])
    desc_alert_vals = await client.walk(PRINTER_OIDS["prtAlertDescription"])
    code_map = {str(k).split(".")[-1]: py_value(v) for k, v in code_vals}
    desc_alert_map = {str(k).split(".")[-1]: py_value(v) for k, v in desc_alert_vals}
    for idx in code_map:
        alerts.append({
            "code": str(code_map.get(idx, "")),
            "description": str(desc_alert_map.get(idx, "")),
        })
    device["alerts"] = alerts

    device["status"] = "online"
    return device


async def run_discovery():
    LOGGER.info("Iniciando descoberta na rede...")
    devices = []
    all_ips = []
    for network in AGENT_CONFIG["networks"]:
        try:
            net = ipaddress.ip_network(network, strict=False)
            all_ips.extend(str(ip) for ip in net.hosts())
        except ValueError:
            all_ips.append(network)

    semaphore = asyncio.Semaphore(30)

    async def check(ip):
        async with semaphore:
            return await probe_device(ip)

    tasks = [asyncio.create_task(check(ip)) for ip in all_ips]
    for task in asyncio.as_completed(tasks):
        try:
            device = await task
            if device:
                devices.append(device)
        except Exception:
            pass

    LOGGER.info("Encontrados %d equipamento(s).", len(devices))
    return devices


def sync_devices(devices):
    payload = {
        "agent_id": AGENT_CONFIG["agent_id"],
        "devices": [],
    }
    for dev in devices:
        payload["devices"].append({
            "ip": dev["ip"],
            "manufacturer": dev.get("manufacturer", ""),
            "model": dev.get("model", ""),
            "serial_number": dev.get("serial_number", ""),
            "hostname": dev.get("sys_name", ""),
            "sys_object_id": dev.get("sys_object_id", ""),
            "sys_location": dev.get("sys_location", ""),
            "sys_contact": dev.get("sys_contact", ""),
            "snmp_version": dev.get("snmp_version", "v2c"),
            "status": {
                "status": dev.get("status", "unknown"),
                "severity": "normal" if dev.get("status") == "online" else "warning",
            },
            "counters": [
                {"name": name, "value": val}
                for name, val in dev.get("counters", {}).items()
                if val is not None
            ],
            "consumables": [
                {
                    "description": str(s.get("description", "")),
                    "max_capacity": s.get("max"),
                    "level": s.get("level"),
                    "percent": round(s["level"] / s["max"] * 100) if s.get("max") and s.get("level") is not None else None,
                }
                for s in dev.get("supplies", [])
            ],
            "errors": [
                {"code": str(e.get("code", "")), "description": str(e.get("description", ""))}
                for e in dev.get("alerts", [])
            ],
        })

    result = api_request("/api/agent/snapshots", payload)
    if result:
        LOGGER.info("Sincronizados %d dispositivo(s).", result.get("devices_processed", 0))
    return result


def send_heartbeat():
    api_request("/api/agent/heartbeat", {"agent_id": AGENT_CONFIG["agent_id"]})


# --- Agent State ---
_agent_running = True
_agent_paused = False


def agent_loop():
    global _agent_running, _agent_paused
    init_db()
    LOGGER.info("Agente iniciado: %s", AGENT_CONFIG["agent_name"])
    LOGGER.info("Servidor: %s", AGENT_CONFIG["server_url"])

    intervals = AGENT_CONFIG["intervals"]
    last_discovery = 0
    last_counters = 0
    last_heartbeat = 0
    devices_cache = []

    while _agent_running:
        if _agent_paused:
            time.sleep(1)
            continue

        now = time.time()

        if now - last_heartbeat >= 60:
            send_heartbeat()
            last_heartbeat = now

        if now - last_discovery >= intervals["discovery"]:
            try:
                loop = asyncio.new_event_loop()
                devices_cache = loop.run_until_complete(run_discovery())
                loop.close()
            except Exception as exc:
                LOGGER.error("Erro na descoberta: %s", exc)
            last_discovery = now

        if now - last_counters >= intervals["counters"] and devices_cache:
            for dev in devices_cache:
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(collect_device(dev))
                    loop.close()
                except Exception as exc:
                    LOGGER.error("Erro ao recolher %s: %s", dev["ip"], exc)
            sync_devices(devices_cache)
            last_counters = now

        time.sleep(10)


# --- Tray Icon ---
def create_tray_icon():
    import pystray
    from PIL import Image, ImageDraw

    def create_image():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([8, 8, 56, 56], fill="#0d6efd", outline="#0a58ca", width=2)
        draw.rectangle([16, 20, 48, 44], fill="white")
        draw.rectangle([20, 48, 44, 52], fill="white")
        return img

    def on_start(icon, item):
        global _agent_paused
        _agent_paused = False
        LOGGER.info("Servico iniciado.")

    def on_pause(icon, item):
        global _agent_paused
        _agent_paused = True
        LOGGER.info("Servico pausado.")

    def on_stop(icon, item):
        global _agent_paused
        _agent_paused = True
        LOGGER.info("Servico parado.")

    def on_exit(icon, item):
        global _agent_running
        _agent_running = False
        icon.stop()

    def build_menu():
        if _agent_paused:
            return pystray.Menu(
                pystray.MenuItem("Iniciar", on_start, default=True),
                pystray.MenuItem("Fechar", on_exit),
            )
        else:
            return pystray.Menu(
                pystray.MenuItem("Pausar", on_pause, default=True),
                pystray.MenuItem("Parar", on_stop),
                pystray.MenuItem("Fechar", on_exit),
            )

    icon = pystray.Icon(
        "FotocopiadoraAgent",
        create_image(),
        DISPLAY_NAME,
        build_menu(),
    )

    def update_menu():
        while _agent_running:
            time.sleep(2)
            try:
                icon.menu = build_menu()
            except Exception:
                pass

    menu_thread = threading.Thread(target=update_menu, daemon=True)
    menu_thread.start()

    return icon


# --- Main ---
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager

    class AgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = DISPLAY_NAME
        _svc_description_ = "Agente de monitoramento de fotocopiadoras"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            global _agent_running
            _agent_running = False
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self):
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ""))
            agent_loop()

    HAS_SERVICE = True
except ImportError:
    HAS_SERVICE = False


def main():
    global _agent_running

    if HAS_SERVICE:
        if len(sys.argv) > 1:
            win32serviceutil.HandleCommandLine(AgentService)
            return

        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(AgentService)
            servicemanager.StartServiceCtrlDispatcher()
            return
        except Exception:
            pass

    agent_thread = threading.Thread(target=agent_loop, daemon=True)
    agent_thread.start()
    icon = create_tray_icon()
    icon.run()


if __name__ == "__main__":
    main()
