# Deploy - Gestao Fotocopiadoras

## Requisitos
- Servidor VPS Ubuntu 22.04+ (DigitalOcean, Hetzner, Contabo, etc.)
- Dominio digitalizacao.net a apontar para o IP do servidor
- Acesso SSH ao servidor

## Passo 1: Preparar o servidor

```bash
# Conectar ao servidor
ssh root@IP_DO_SERVIDOR

# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias
sudo apt install -y python3 python3-pip python3-venv nginx git certbot python3-certbot-nginx
```

## Passo 2: Clonar o repositorio

```bash
cd /opt
sudo git clone https://github.com/leiturasproficopia-alt/GestaoFotocopiadoras.git fotocopiadora
sudo chown -R $USER:$USER /opt/fotocopiadora
```

## Passo 3: Configurar a aplicacao

```bash
cd /opt/fotocopiadora

# Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install fastapi uvicorn jinja2 python-multipart aiofiles pysnmp

# Testar se funciona
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
# Ctrl+C para parar
```

## Passo 4: Criar servico systemd

```bash
sudo tee /etc/systemd/system/fotocopiadora.service > /dev/null << EOF
[Unit]
Description=Gestao Fotocopiadoras Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/opt/fotocopiadora
ExecStart=/opt/fotocopiadora/venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Ativar e iniciar
sudo systemctl daemon-reload
sudo systemctl enable fotocopiadora
sudo systemctl start fotocopiadora

# Verificar estado
sudo systemctl status fotocopiadora
```

## Passo 5: Configurar Nginx

```bash
sudo tee /etc/nginx/sites-available/fotocopiadora > /dev/null << 'EOF'
server {
    listen 80;
    server_name digitalizacao.net www.digitalizacao.net;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name digitalizacao.net www.digitalizacao.net;

    ssl_certificate /etc/letsencrypt/live/digitalizacao.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/digitalizacao.net/privkey.pem;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/fotocopiadora/server/static/;
        expires 30d;
    }

    access_log /var/log/nginx/fotocopiadora_access.log;
    error_log /var/log/nginx/fotocopiadora_error.log;
}
EOF

# Ativar site
sudo ln -s /etc/nginx/sites-available/fotocopiadora /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## Passo 6: Configurar SSL (HTTPS)

```bash
# Certificado temporario primeiro (sem HTTPS)
sudo tee /etc/nginx/sites-available/fotocopiadora > /dev/null << 'EOF'
server {
    listen 80;
    server_name digitalizacao.net www.digitalizacao.net;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

sudo systemctl reload nginx

# Obter certificado SSL
sudo certbot --nginx -d digitalizacao.net -d www.digitalizacao.net

# O certbot configura automaticamente o Nginx com SSL
```

## Passo 7: Configurar firewall

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw enable
```

## Passo 8: Testar

1. Acessar https://digitalizacao.net
2. Login: admin / admin
3. Criar um agente
4. Descarregar o EXE e instalar num cliente

## Comandos uteis

```bash
# Ver logs
sudo journalctl -u fotocopiadora -f

# Reiniciar aplicacao
sudo systemctl restart fotocopiadora

# Ver logs do Nginx
sudo tail -f /var/log/nginx/fotocopiadora_error.log

# Atualizar codigo
cd /opt/fotocopiadora
git pull
sudo systemctl restart fotocopiadora
```

## Backup da base de dados

```bash
# Backup manual
cp /opt/fotocopiadora/server/data/server.db /opt/fotocopiadora/backups/server_$(date +%Y%m%d).db

# Backup automatico (crontab)
crontab -e
# Adicionar: 0 2 * * * cp /opt/fotocopiadora/server/data/server.db /opt/fotocopiadora/backups/server_$(date +\%Y\%m\%d).db
```
