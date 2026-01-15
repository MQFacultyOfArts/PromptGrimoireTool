# Plan: Document Deployment Setup

## Summary
Create deployment documentation based on the server configuration discovered from the production server `google-eald-v2-prod`.

## Files to Create
1. `docs/deployment.md` - Complete deployment guide
2. `docs/eald.service` - systemd service file (copy from server)
3. `docs/haproxy.cfg` - HAProxy config template
4. `docs/certbot-haproxy-deploy.sh` - Certbot renewal hook (TO BE INSTALLED on server)

---

## Implementation Steps

### Step 1: Create `docs/deployment.md`

Full deployment guide covering:

**Infrastructure:**
- Server: Google Cloud VM (Ubuntu 24.04)
- Hostname: `google-eald-v2-prod`
- App location: `/opt/eald-app`
- Domain: `brian.fedarch.org`
- Repo: `git@github.com:MQFacultyOfArts/ai-lang-tool-eald-prototype.git`

**Stack:**
- App: NiceGUI via `uv run python examples/example9_audio_pipeline/main.py`
- Process manager: systemd (`eald.service`)
- Reverse proxy: HAProxy (TLS termination, HTTP→HTTPS redirect)
- Database: PostgreSQL (`eald_vocab` db, `eald` user)
- SSL: Let's Encrypt via certbot

**systemd service** (`/etc/systemd/system/eald.service`):
```ini
[Unit]
Description=EAL/D Vocabulary Learning Application
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/eald-app
ExecStart=/bin/bash -c 'set -a; source /opt/eald-app/.env; set +a; /home/ubuntu/.local/bin/uv run python examples/example9_audio_pipeline/main.py'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**HAProxy config** - TLS 1.2+, modern ciphers, HSTS, forwards to localhost:8080

**Initial deployment steps:**
1. Create `/opt/eald-app`, clone repo via SSH
2. Copy `.envrc.sample` to `.env`, fill in production values
3. Install `uv`, run `uv sync`
4. Install systemd service, enable and start
5. Install HAProxy, certbot
6. Get cert, combine for HAProxy, configure, start
7. Install certbot renewal hook

**Operational commands:**
- Update: `cd /opt/eald-app && git pull && sudo systemctl restart eald`
- Logs: `journalctl -u eald -f`
- Status: `sudo systemctl status eald haproxy`

### Step 2: Create `docs/eald.service`
Copy of the systemd unit file for reference/reinstall.

### Step 3: Create `docs/haproxy.cfg`
Template HAProxy config (with `YOUR_DOMAIN` placeholder).

### Step 4: Create `docs/certbot-haproxy-deploy.sh`
Renewal hook script to combine certs and reload HAProxy:
```bash
#!/bin/bash
DOMAIN="brian.fedarch.org"
cat /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    > /etc/haproxy/certs/$DOMAIN.pem
chmod 600 /etc/haproxy/certs/$DOMAIN.pem
systemctl reload haproxy
```

**ACTION REQUIRED:** The deploy hook is missing on the server. Certbot timer runs but won't update HAProxy's combined PEM.

Install on server:
```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/haproxy.sh << 'EOF'
#!/bin/bash
DOMAIN="brian.fedarch.org"
cat /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    > /etc/haproxy/certs/$DOMAIN.pem
chmod 600 /etc/haproxy/certs/$DOMAIN.pem
systemctl reload haproxy
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/haproxy.sh
```

---

## Verification
1. Review created docs for accuracy
2. Brian to install the certbot hook on server

## Post-Implementation
- Mark `[ ] Create deployment guide` as complete in `docs/TASKS.md`
