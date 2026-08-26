#!/bin/bash
# Script de deploy para servidor
# Execute no VPS/servidor com Ubuntu

set -e

echo "=== Configurando Gestao Fotocopiadoras ==="

# Instalar dependencias do sistema
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Criar usuario para o servico
sudo useradd -r -s /bin/false fotocopiadora || true

# Diretorio da aplicacao
APP_DIR="/opt/fotocopiadora"
sudo mkdir -p $APP_DIR
sudo cp -r . $APP_DIR/
sudo chown -R fotocopiadora:fotocopiadora $APP_DIR

# Ambiente virtual
cd $APP_DIR
sudo -u fotocopiadora python3 -m venv venv
sudo -u fotocopiadora venv/bin/pip install --upgrade pip
sudo -u fotocopiadora venv/bin/pip install fastapi uvicorn jinja2 python-multipart aiofiles pysnmp

# Servico systemd
sudo tee /etc/systemd/system/fotocopiadora.service > /dev/null << EOF
[Unit]
Description=Gestao Fotocopiadoras Server
After=network.target

[Service]
Type=simple
User=fotocopiadora
Group=fotocopiadora
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Iniciar servico
sudo systemctl daemon-reload
sudo systemctl enable fotocopiadora
sudo systemctl restart fotocopiadora

echo ""
echo "=== Servidor configurado! ==="
echo "Proximo passo: configurar Nginx"
