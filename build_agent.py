"""
Build agent.py from template using environment variables.
Used by GitHub Actions workflow.
"""
import json
import os
from pathlib import Path


def build():
    agent_id = os.environ.get("AGENT_ID", "")
    agent_name = os.environ.get("AGENT_NAME", "Agente")
    server_url = os.environ.get("SERVER_URL", "http://localhost:8000")
    api_token = os.environ.get("API_TOKEN", "")
    networks = os.environ.get("NETWORKS", '["192.168.1.0/24"]')
    discovery_seconds = os.environ.get("DISCOVERY_SECONDS", "14400")
    counters_seconds = os.environ.get("COUNTERS_SECONDS", "14400")
    supplies_seconds = os.environ.get("SUPPLIES_SECONDS", "3600")
    alerts_seconds = os.environ.get("ALERTS_SECONDS", "3600")
    attributes_seconds = os.environ.get("ATTRIBUTES_SECONDS", "43200")

    template_path = Path(__file__).parent / "server" / "agent_standalone.py"
    if not template_path.exists():
        print(f"ERROR: Template not found at {template_path}")
        return

    code = template_path.read_text(encoding="utf-8")

    replacements = {
        "{{AGENT_ID}}": agent_id,
        "{{AGENT_NAME}}": agent_name,
        "{{SERVER_URL}}": server_url,
        "{{API_TOKEN}}": api_token,
        "{{NETWORKS}}": networks,
        "{{DISCOVERY_SECONDS}}": discovery_seconds,
        "{{COUNTERS_SECONDS}}": counters_seconds,
        "{{SUPPLIES_SECONDS}}": supplies_seconds,
        "{{ALERTS_SECONDS}}": alerts_seconds,
        "{{ATTRIBUTES_SECONDS}}": attributes_seconds,
    }

    for placeholder, value in replacements.items():
        code = code.replace(placeholder, value)

    output = Path(__file__).parent / "agent.py"
    output.write_text(code, encoding="utf-8")
    print(f"Generated {output} ({len(code)} bytes)")


if __name__ == "__main__":
    build()
