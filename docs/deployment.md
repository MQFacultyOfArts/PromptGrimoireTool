# Deployment Guide — PromptGrimoire

*Last updated: 2026-03-01*
*Target: NCI Cloud VM — Ubuntu 24.04 LTS, 4 vCPU / 8GB RAM, 60GB boot volume, grimoire.drbbs.org*

## Architecture Overview

```
                        ┌─────────────────────┐
┌─────────┐             │      HAProxy        │
│ Browser  │────────────▶│  :80 → 301 → :443  │
│ (HTTPS)  │◀────────────│  :443 TLS terminate │
└─────────┘             └─────────┬───────────┘
                                  │
                        ┌─────────▼───────────┐      ┌────────────┐
                        │   promptgrimoire    │─────▶│ PostgreSQL │
                        │   :8080 (uvicorn)   │◀─────│ :5432      │
                        │                     │      └────────────┘
                        │   search_worker     │
                        │   (asyncio task)    │      ┌────────────┐
                        └─────────────────────┘      │ External   │
                                                     │ - Stytch   │
                                                     │ - Claude   │
          ┌──────────────────────────────┐           └────────────┘
          │ fail2ban  │ UFW   │ certbot  │
          │ (IPS)     │ (fw)  │ (certs)  │
          └──────────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │ rclone → SharePoint│
              │ (nightly backup)   │
              └────────────────────┘
```

Single process: NiceGUI runs on uvicorn, search worker runs as an internal asyncio task. No separate worker service needed.

**Recovery time objective:** ~1 day (rebuild VM from this guide + restore DB from SharePoint backup).

---

## 0. NCI Cloud VM Setup

Provision a new instance via the NCI Cloud dashboard (OpenStack).

- **Image:** Ubuntu 24.04 LTS
- **Flavour:** 4 vCPU / 8GB RAM / 60GB boot disk
- **Security groups:** Allow inbound TCP 22 (SSH), 80 (HTTP), 443 (HTTPS)
- **Key pair:** Your SSH key
- **Floating IP:** Assign a public IP, then point `grimoire.drbbs.org` A record to it
- **Customisation script:** Leave empty — manual setup from this guide

**Disk layout:** Single 60GB Cinder boot volume at `/dev/vda`, mounted at `/`. Everything lives on root. Instance termination loses disk — restore from SharePoint backup (Step 14).

```bash
ssh ubuntu@<floating-ip>
```

**DNS:** Set the `grimoire.drbbs.org` A record to the floating IP now. Certbot (Step 12) requires DNS to resolve. Propagation can take minutes to hours.

**Terminal:** If using Ghostty, copy the terminfo to the server before doing anything else. The remote won't have the `xterm-ghostty` entry, and byobu/tmux/ncurses tools will break without it.

```bash
# From your LOCAL machine (not the server)
infocmp -x xterm-ghostty | ssh ubuntu@<floating-ip> 'tic -x -'
```

Verify after SSH-ing in: `echo $TERM` should show `xterm-ghostty` and `tput colors` should return `256`.

> **Ref:** [NCI Cloud User Guide](https://opus.nci.org.au/display/Help/Cloud+User+Guide), [Ghostty terminfo](https://ghostty.org/docs/help/terminfo)

---

## 1. System Packages

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
  git \
  haproxy \
  certbot \
  postgresql postgresql-contrib \
  fail2ban \
  ufw \
  unattended-upgrades apt-listchanges \
  pandoc \
  curl \
  fontconfig

# rclone — install from upstream (apt version lags badly)
curl https://rclone.org/install.sh | sudo bash
rclone version
```

> **Ref:** [Ubuntu 24.04 Package Management](https://documentation.ubuntu.com/server/explanation/software/package-management/)

## 2. SSH Hardening

**Do this first, before exposing any services.**

Create `/etc/ssh/sshd_config.d/99-hardened.conf`:

```
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

```bash
# Test config before applying (KEEP YOUR CURRENT SESSION OPEN)
sudo sshd -t
sudo systemctl restart ssh  # Ubuntu 24.04 uses ssh.service, not sshd.service
```

> **Ref:** [OpenSSH sshd_config(5)](https://man.openbsd.org/sshd_config), [Ubuntu SSH hardening](https://documentation.ubuntu.com/server/how-to/security/openssh-server/)

## 3. UFW Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH before enabling (critical — don't lock yourself out)
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

sudo ufw enable
sudo ufw status verbose
```

NCI security groups provide an outer firewall; UFW provides host-level defence in depth.

> **Ref:** [UFW manual](https://manpages.ubuntu.com/manpages/noble/en/man8/ufw.8.html), [DigitalOcean UFW Essentials](https://www.digitalocean.com/community/tutorials/ufw-essentials-common-firewall-rules-and-commands)

## 4. Timezone + Unattended Security Updates

```bash
# Set timezone (default is UTC — 4am UTC = 3pm AEDT, middle of class)
sudo timedatectl set-timezone Australia/Sydney
timedatectl  # verify: should show Australia/Sydney (AEDT, +1100)

sudo dpkg-reconfigure -plow unattended-upgrades  # select "Yes"
```

Edit `/etc/apt/apt.conf.d/50unattended-upgrades`:

```
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
```

```bash
# Verify
sudo unattended-upgrade -v --dry-run
```

> **Ref:** [Ubuntu Automatic Updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)

## 5. uv + Python 3.14

uv manages both package installation and the Python runtime itself. No system Python 3.14 needed — uv downloads a standalone build from `python-build-standalone` (includes headers for C extension compilation).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env  # adds ~/.local/bin to PATH, or restart shell

# Download Python 3.14
uv python install 3.14

# Verify both
uv --version
uv python list | grep 3.14
```

> **Ref:** [uv installation](https://docs.astral.sh/uv/getting-started/installation/), [uv Python management](https://docs.astral.sh/uv/guides/install-python/), [python-build-standalone](https://github.com/astral-sh/python-build-standalone)

## 6. Benchmark Disk I/O

All data lives on the 60GB Cinder boot volume (`/dev/vda1` mounted at `/`). Benchmark before configuring PostgreSQL — results inform buffer tuning.

```bash
# Sequential write (pg_dump, LaTeX output)
fio --name=seqwrite --rw=write --bs=1M --size=1G --numjobs=1 \
    --directory=/tmp --runtime=30 --group_reporting

# Random 4K read/write (PostgreSQL OLTP)
fio --name=randmix --rw=randrw --bs=4k --size=256M --numjobs=4 \
    --directory=/tmp --runtime=30 --group_reporting

# Latency
ioping -c 20 /

# Clean up benchmark files
rm -f /tmp/seqwrite.0.0 /tmp/randmix.*.0
```

NCI Cinder (likely Ceph-backed): expect ~100–200 MB/s sequential, ~5k–10k random IOPS, ~0.5–2ms latency. Record these numbers — they feed into PostgreSQL tuning in Step 7.

> **Ref:** [fio documentation](https://fio.readthedocs.io/en/latest/)

## 7. PostgreSQL

PostgreSQL data lives at the default `/var/lib/postgresql/` on the boot volume.

```bash
# Create the application user and database
sudo -u postgres createuser --createdb promptgrimoire
sudo -u postgres createdb -O promptgrimoire promptgrimoire

# Verify (the DB and role exist — peer auth tested after Step 8 creates the system user)
sudo -u postgres psql -d promptgrimoire -c "SELECT 1;"
```

The `promptgrimoire` system user (created in Step 8) authenticates via `peer` — no password needed for local Unix socket connections. Peer auth verification:

```bash
# Run this AFTER Step 8 (service user must exist first)
sudo -u promptgrimoire psql -d promptgrimoire -c "SELECT 1;"
```

> **Ref:** [PostgreSQL 16 createuser](https://www.postgresql.org/docs/16/app-createuser.html), [pg_hba.conf auth methods](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html)

## 8. Application Setup

```bash
# Create service user
sudo useradd --system --home /home/promptgrimoire --create-home \
  --shell /usr/sbin/nologin promptgrimoire
```

### GitHub deploy key

The repo is private under `MQFacultyOfArts`. Generate an SSH deploy key so the service user can pull.

```bash
# Generate a key for the service user (no passphrase)
sudo -u promptgrimoire ssh-keygen -t ed25519 -C "promptgrimoire@grimoire.drbbs.org" \
  -f /home/promptgrimoire/.ssh/id_ed25519 -N ""

# Print the public key
sudo cat /home/promptgrimoire/.ssh/id_ed25519.pub
```

Add the public key as a **deploy key** in GitHub:
1. Go to `https://github.com/MQFacultyOfArts/PromptGrimoireTool/settings/keys`
2. Click "Add deploy key"
3. Paste the public key, title it `grimoire.drbbs.org`
4. Leave "Allow write access" **unchecked** (read-only is sufficient for pulls)

```bash
# Test SSH connectivity
sudo -u promptgrimoire ssh -T git@github.com
# Should say: "Hi MQFacultyOfArts/PromptGrimoireTool! You've successfully authenticated..."
```

> **Ref:** [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#deploy-keys)

### Clone and install

```bash
# Clone repo (SSH URL, not HTTPS)
sudo mkdir -p /opt/promptgrimoire
sudo chown promptgrimoire:promptgrimoire /opt/promptgrimoire
sudo -u promptgrimoire git clone \
  git@github.com:MQFacultyOfArts/PromptGrimoireTool.git \
  /opt/promptgrimoire

cd /opt/promptgrimoire

# Install uv for the service user
sudo -u promptgrimoire bash -c \
  'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Install dependencies (no dev/test deps in production)
sudo -u promptgrimoire /home/promptgrimoire/.local/bin/uv sync --no-dev

# Create .env from template
sudo -u promptgrimoire cp .env.example .env
```

### Configure `.env`

Edit `/opt/promptgrimoire/.env`:

```bash
# Database — Unix socket (peer auth, no password)
DATABASE__URL=postgresql+asyncpg://promptgrimoire@/promptgrimoire?host=/var/run/postgresql

# Stytch — use LIVE keys, not test keys
STYTCH__PROJECT_ID=project-live-...
STYTCH__SECRET=secret-live-...
STYTCH__PUBLIC_TOKEN=public-token-live-...
STYTCH__DEFAULT_ORG_ID=organization-live-...
STYTCH__SSO_CONNECTION_ID=saml-connection-live-...

# App
APP__BASE_URL=https://grimoire.drbbs.org
APP__PORT=8080
APP__STORAGE_SECRET=  # generate: python3.14 -c "import secrets; print(secrets.token_urlsafe(32))"

# Claude API
LLM__API_KEY=sk-ant-...

# Production settings
DEV__AUTH_MOCK=false
DEV__ENABLE_DEMO_PAGES=false
DEV__BRANCH_DB_SUFFIX=false
```

### Authentication Services

The app supports four login methods. All are mediated through Stytch B2B.

| Method | Audience | Stytch Feature | Config Needed |
|--------|----------|----------------|---------------|
| **AAF OIDC** (primary) | All MQ staff + students | SSO → generic OIDC connection | AAF registration + Stytch OIDC connection |
| **Google OAuth** (backstop) | Students who can't AAF | OAuth provider | Stytch dashboard toggle + Google Cloud OAuth credentials |
| **Magic Link** (back-backstop) | Edge cases | Email magic links | Domain-restricted in code to `mq.edu.au`, `students.mq.edu.au` |
| **GitHub OAuth** (dev) | Brian | OAuth provider | Already configured |

#### AAF OIDC Setup

AAF (Australian Access Federation) provides federated SSO for Australian universities. MQ uses AAF Rapid IdP. The app registers as an OIDC relying party via Stytch.

**1. Register with AAF** at [Federation Manager](https://manager.aaf.edu.au/) (production) or [test federation](https://manager.test.aaf.edu.au/) (free, instant):

- **Name:** PromptGrimoire
- **Description:** Collaborative annotation platform
- **URL:** `https://grimoire.drbbs.org`
- **Redirect URL:** Get this from Stytch after creating the OIDC connection (Step 3 below)
- **Authentication method:** Secret
- **Organisation:** Macquarie University

You receive a **Client ID** and **Client Secret**. The secret is shown only once — copy it immediately. Production registrations take ~2 hours to propagate.

**Scopes** to request (configure in AAF Federation Manager → Scopes tab):

```
openid profile email eduperson_affiliation schac_home_organization
```

`eduperson_affiliation` is critical — it carries `staff`/`faculty`/`student`, which the app maps to the `instructor` role via `derive_roles_from_metadata()`.

**2. Create Stytch Organisation** in the [Stytch dashboard](https://stytch.com/dashboard):

- **Name:** Macquarie University
- **Slug:** `mq`
- **Allowed auth methods:** Email Magic Links, SSO, Google OAuth, GitHub OAuth
- **JIT provisioning domains:** `mq.edu.au`, `students.mq.edu.au`

Record the `organization-live-...` ID for `STYTCH__DEFAULT_ORG_ID` in `.env`.

**3. Create OIDC Connection** in Stytch → SSO → Create Connection:

| Field | Value |
|-------|-------|
| Identity Provider | Generic OIDC |
| Display Name | AAF |
| Issuer | `https://central.aaf.edu.au` |
| Client ID | From AAF registration |
| Client Secret | From AAF registration |
| Custom Scopes | `openid profile email eduperson_affiliation schac_home_organization` |

Stytch generates a **Redirect URL** — copy this back to your AAF registration as the redirect URI.

Configure **attribute mapping** in Stytch to flow `eduperson_affiliation` and `schac_home_organization` into `trusted_metadata`.

Record the `saml-connection-live-...` ID for `STYTCH__SSO_CONNECTION_ID` in `.env`.

**4. Test the flow:**
- Navigate to `https://grimoire.drbbs.org`
- Click "Login with AAF"
- Authenticate via MQ OneID
- Should return to app with active session
- Staff users should have `instructor` role (check via `manage-users show`)

#### Google OAuth Setup

**1. Create OAuth credentials** in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

- **Application type:** Web application
- **Authorized redirect URI:** Get from Stytch dashboard (OAuth → Google → Redirect URL)

**2. Enable in Stytch** dashboard → OAuth → Google:

- Enter Google Client ID and Client Secret
- JIT provisioning is controlled by the organisation's email domain settings

#### JIT Provisioning Bootstrap

Stytch email domain JIT provisioning requires at least one existing member with a verified email from each allowed domain. Before students can self-provision via Google OAuth:

1. Manually create one member with `@students.mq.edu.au` email (via magic link or `manage-users create`)
2. After that, student JIT works automatically

> **Ref:** [AAF OIDC Integration](https://tutorials.aaf.edu.au/openid-connect-integration), [AAF Federation Manager](https://manager.aaf.edu.au/), [AAF Test Federation](https://manager.test.aaf.edu.au/), [Stytch B2B SSO](https://stytch.com/docs/b2b/guides/sso/overview), [Stytch OAuth](https://stytch.com/docs/b2b/guides/oauth/overview)
>
> **Cached docs:** `docs/aaf/oidc-integration.md`, `docs/aaf/test-federation.md`, `docs/aaf/rapid-idp.md`
>
> **Design plan:** `docs/design-plans/2026-02-26-aaf-oidc-auth-188-189.md`

### Service user profile

The `promptgrimoire` user has `/usr/sbin/nologin` as its shell, so it needs an explicit `.profile` for PATH setup. This ensures TinyTeX and uv are found both by systemd and by `grimoire-run`.

```bash
echo 'export PATH="/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:/home/promptgrimoire/.local/bin:$PATH"' \
  | sudo tee /home/promptgrimoire/.profile
sudo chown promptgrimoire:promptgrimoire /home/promptgrimoire/.profile
```

### `grimoire-run` helper

All `uv run` commands for the service user must execute from `/opt/promptgrimoire` — uv walks up the directory tree looking for config files and will fail with permission errors if run from `/home/ubuntu` or elsewhere. This wrapper handles the `cd`, `sudo`, and PATH boilerplate.

Create `/usr/local/bin/grimoire-run`:

```bash
#!/bin/bash
# Run a command in the PromptGrimoire venv as the service user.
# Sources the service user's profile for PATH (TinyTeX, uv).
cd /opt/promptgrimoire
exec sudo -u promptgrimoire \
  env PATH="/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:/home/promptgrimoire/.local/bin:/usr/local/bin:/usr/bin:/bin" \
  /home/promptgrimoire/.local/bin/uv run "$@"
```

```bash
sudo chmod +x /usr/local/bin/grimoire-run
```

### Run Migrations

```bash
# Migrations run automatically on app start, but can be run manually:
grimoire-run alembic upgrade head
```

## 9. TinyTeX (PDF Export)

Install system fonts first (Noto provides broad Unicode coverage, SIL fonts cover specialist scripts). This is a large download (~1GB for Noto CJK).

```bash
sudo apt install -y fonts-noto --install-recommends \
  fonts-texgyre \
  fonts-sil-gentiumplus fonts-sil-charis fonts-sil-doulos \
  fonts-sil-scheherazade fonts-sil-ezra fonts-sil-annapurna \
  fonts-sil-abyssinica fonts-sil-padauk fonts-sil-mondulkiri \
  fonts-sil-galatia fonts-sil-sophia-nubian fonts-sil-nuosusil \
  fonts-sil-taiheritagepro
```

Then install TinyTeX (installs to `~/.TinyTeX` by default, no relocation needed):

```bash
sudo -u promptgrimoire bash -c \
  'cd /opt/promptgrimoire && /home/promptgrimoire/.local/bin/uv run python scripts/setup_latex.py'
```

Rebuild the LuaTeX font cache so fontspec can find system fonts (especially TeX Gyre Termes):

```bash
cd /opt/promptgrimoire
sudo -u promptgrimoire env PATH="/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:$PATH" \
  luaotfload-tool --update --force
```

Verify:

```bash
# latexmk is installed
sudo -u promptgrimoire /home/promptgrimoire/.TinyTeX/bin/x86_64-linux/latexmk --version

# LuaTeX can find the main font (OSFONTDIR must be set)
cd /opt/promptgrimoire
sudo -u promptgrimoire env \
  PATH="/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:$PATH" \
  OSFONTDIR="/usr/share/fonts:/usr/share/texmf/fonts" \
  luaotfload-tool --update --force
sudo -u promptgrimoire env \
  PATH="/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:$PATH" \
  OSFONTDIR="/usr/share/fonts:/usr/share/texmf/fonts" \
  luaotfload-tool --find="TeX Gyre Termes"
# Should print the font path, NOT "Cannot find"

# System sees the font
fc-list | grep -i "tex gyre termes"
```

If `luaotfload-tool --find` can't find fonts that `fc-list` sees, check `$OSFONTDIR` — LuaTeX does **not** use fontconfig. It only scans its own texmf tree plus directories listed in `OSFONTDIR`. The systemd service sets this; for manual invocations pass it via `env`.

```bash
cd /opt/promptgrimoire
sudo -u promptgrimoire env \
  PATH="/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:$PATH" \
  OSFONTDIR="/usr/share/fonts:/usr/share/texmf/fonts" \
  luaotfload-tool --diagnose=environment
```

> **Ref:** [TinyTeX installation](https://yihui.org/tinytex/)

## 10. systemd Service

Create `/etc/systemd/system/promptgrimoire.service`:

```ini
[Unit]
Description=PromptGrimoire — collaborative annotation platform
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=promptgrimoire
Group=promptgrimoire
WorkingDirectory=/opt/promptgrimoire
Environment=PATH=/home/promptgrimoire/.local/bin:/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/promptgrimoire
Environment=OSFONTDIR=/usr/share/fonts:/usr/share/texmf/fonts
ExecStart=/home/promptgrimoire/.local/bin/uv run python run_prod.py
Restart=on-failure
RestartSec=5
SuccessExitStatus=143

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=promptgrimoire

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/promptgrimoire/logs /opt/promptgrimoire/.venv /home/promptgrimoire/.TinyTeX /home/promptgrimoire/.cache/uv
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Ensure the uv cache directory exists before starting (systemd's `ReadWritePaths` can't create it):

```bash
sudo -u promptgrimoire mkdir -p /home/promptgrimoire/.cache/uv

sudo systemctl daemon-reload
sudo systemctl enable promptgrimoire
sudo systemctl start promptgrimoire

# Verify
sudo systemctl status promptgrimoire
sudo journalctl -u promptgrimoire -f
```

> **Ref:** [systemd.service(5)](https://www.freedesktop.org/software/systemd/man/systemd.service.html), [systemd.exec(5) sandboxing](https://www.freedesktop.org/software/systemd/man/systemd.exec.html#Sandboxing)

## 11. HAProxy

HAProxy terminates TLS and reverse-proxies to the app. WebSocket upgrade is handled natively.

Create `/etc/haproxy/haproxy.cfg`:

```haproxy
global
    log /dev/log local0
    log /dev/log local1 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy
    daemon

    # TLS tuning
    ssl-default-bind-ciphersuites TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256
    ssl-default-bind-options ssl-min-ver TLSv1.2 no-tls-tickets
    tune.ssl.default-dh-param 2048

defaults
    log     global
    mode    http
    option  dontlognull
    option  http-server-close
    option  forwardfor

    timeout connect 5s
    timeout client  25s
    timeout server  25s
    timeout tunnel  3600s
    timeout http-keep-alive 1s
    timeout http-request 15s

    # Custom log format with client IP for fail2ban (replaces option httplog)
    log-format "%ci:%cp [%tr] %ft %b/%s %TR/%Tw/%Tc/%Tr/%Ta %ST %B %CC %CS %tsc %ac/%fc/%bc/%sc/%rc %sq/%bq %hr %hs %{+Q}r"

frontend fe_http
    bind *:80

    # Let's Encrypt ACME http-01 challenges pass through to certbot
    acl is_acme path_beg /.well-known/acme-challenge/

    # Redirect must come before use_backend to avoid ordering warning
    redirect scheme https code 301 if !is_acme
    use_backend be_certbot if is_acme

backend be_certbot
    # During renewal (~30s every 60-90 days), certbot runs a temporary
    # standalone server on 8402. No health check — nothing listens
    # between renewals, and that's fine.
    server certbot 127.0.0.1:8402

frontend fe_https
    bind *:443 ssl crt /etc/haproxy/certs/grimoire.drbbs.org.pem alpn h2,http/1.1

    # Security headers
    http-response set-header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    http-response set-header X-Content-Type-Options "nosniff"
    http-response set-header X-Frame-Options "DENY"
    http-response set-header Referrer-Policy "strict-origin-when-cross-origin"

    default_backend be_promptgrimoire

backend be_promptgrimoire
    server app 127.0.0.1:8080 check

    # Forward original client info
    http-request set-header X-Forwarded-Proto https
    http-request set-header X-Real-IP %[src]
```

**Key configuration points:**

- `timeout tunnel 3600s` — keeps WebSocket connections alive for up to 1 hour idle. NiceGUI WebSockets are long-lived; this prevents premature disconnects.
- `option http-server-close` — enables HTTP keep-alive reuse while closing server connections cleanly.
- `alpn h2,http/1.1` — enables HTTP/2 for regular requests; WebSocket upgrade falls back to HTTP/1.1 automatically.

> **Ref:** [HAProxy WebSocket configuration](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/protocol-support/websocket/), [HAProxy SSL termination](https://www.haproxy.com/blog/haproxy-ssl-termination), [HAProxy timeout tuning](https://www.haproxy.com/blog/the-four-essential-sections-of-an-haproxy-configuration)

## 12. Let's Encrypt + Certificate Smush (Zero Downtime)

HAProxy requires a single PEM file containing the full chain and private key concatenated. Certbot handles the HTTP-01 challenge itself — during renewal, it briefly starts a standalone server on `127.0.0.1:8402`. HAProxy's `fe_http` frontend routes `/.well-known/acme-challenge/` requests to this backend. No persistent webroot service needed.

### Initial certificate

HAProxy isn't running yet (no cert to bind). For the *first* certificate only, use standalone on port 80:

```bash
sudo certbot certonly --standalone -d grimoire.drbbs.org
```

### Smush script and renewal hooks

Set up all the plumbing before starting HAProxy — the smush script, deploy hook, and renewal config. This way everything is ready for both the initial start and future auto-renewals.

Create `/usr/local/bin/haproxy-cert-smush`:

```bash
#!/bin/bash
# Combine Let's Encrypt PEM files into HAProxy's expected single-file format.
# fullchain.pem must come before privkey.pem.
#
# Ref: https://www.haproxy.com/blog/haproxy-ssl-termination
# Ref: https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates
set -euo pipefail

DOMAIN="${1:-grimoire.drbbs.org}"
LE_DIR="/etc/letsencrypt/live/${DOMAIN}"
OUT_DIR="/etc/haproxy/certs"
OUT_FILE="${OUT_DIR}/${DOMAIN}.pem"

if [ ! -d "$LE_DIR" ]; then
    echo "ERROR: Certificate directory not found: $LE_DIR" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
cat "${LE_DIR}/fullchain.pem" "${LE_DIR}/privkey.pem" > "$OUT_FILE"
chmod 600 "$OUT_FILE"

# Validate HAProxy config before reload
if haproxy -c -f /etc/haproxy/haproxy.cfg 2>/dev/null; then
    systemctl reload haproxy
    echo "OK: ${OUT_FILE} updated, HAProxy reloaded"
else
    echo "ERROR: HAProxy config validation failed — cert updated but HAProxy NOT reloaded" >&2
    exit 1
fi
```

```bash
sudo chmod +x /usr/local/bin/haproxy-cert-smush
```

Create the deploy hook at `/etc/letsencrypt/renewal-hooks/deploy/50-haproxy.sh`:

```bash
#!/bin/bash
# After certbot renews, smush the new cert and reload HAProxy.
/usr/local/bin/haproxy-cert-smush
```

```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/50-haproxy.sh
```

Configure renewals to use standalone on port 8402 (behind HAProxy). Edit `/etc/letsencrypt/renewal/grimoire.drbbs.org.conf` and ensure:

```ini
[renewalparams]
authenticator = standalone
http01_port = 8402
```

### Start HAProxy

```bash
# Create the initial combined PEM
sudo /usr/local/bin/haproxy-cert-smush

# Start HAProxy (it now has a cert to bind)
sudo systemctl enable haproxy
sudo systemctl start haproxy
```

### Verify auto-renewal

```bash
sudo certbot renew --dry-run
```

Certbot's systemd timer (`certbot.timer`) runs twice daily. On renewal: certbot starts a temporary server on `127.0.0.1:8402`, HAProxy routes the ACME challenge to it, certbot validates and writes new certs, the deploy hook smushs them into the combined PEM, and `systemctl reload haproxy` picks up the new cert — all without dropping a single connection. The temporary server shuts down after validation (~30 seconds).

> **Ref:** [certbot standalone plugin](https://eff-certbot.readthedocs.io/en/stable/using.html#standalone), [certbot deploy hooks](https://eff-certbot.readthedocs.io/en/stable/using.html#pre-and-post-validation-hooks), [Let's Encrypt HTTP-01 challenge](https://letsencrypt.org/docs/challenge-types/#http-01-challenge)

## 13. fail2ban

### HAProxy log setup

Ubuntu 24.04 ships `/etc/rsyslog.d/49-haproxy.conf` out of the box — it creates a Unix socket in HAProxy's chroot and routes logs to `/var/log/haproxy.log`. Verify it exists:

```bash
cat /etc/rsyslog.d/49-haproxy.conf
# Should show: $AddUnixListenSocket, :programname filter, /var/log/haproxy.log
```

If missing, create it:

```
# Create an additional socket in haproxy's chroot in order to allow logging via
# /dev/log to chroot'ed HAProxy processes
$AddUnixListenSocket /var/lib/haproxy/dev/log

# Send HAProxy messages to a dedicated logfile
:programname, startswith, "haproxy" {
  /var/log/haproxy.log
  stop
}
```

```bash
sudo systemctl restart rsyslog
```

### fail2ban configuration

Create `/etc/fail2ban/jail.local`:

```ini
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3
bantime = 1h

[haproxy-http-flood]
enabled = true
port = http,https
logpath = /var/log/haproxy.log
maxretry = 50
findtime = 30s
bantime = 10m
```

Create `/etc/fail2ban/filter.d/haproxy-http-flood.conf`:

```ini
# Ban IPs making excessive requests through HAProxy.
# Matches the custom log-format in haproxy.cfg: "%ci:%cp [%tr] ..."
[Definition]
failregex = ^<HOST>:\d+ \[
ignoreregex =
```

```bash
sudo systemctl enable fail2ban
sudo systemctl restart fail2ban

# Verify
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

> **Ref:** [fail2ban documentation](https://www.fail2ban.org/wiki/index.php/MANUAL_0_8), [fail2ban HAProxy filter](https://github.com/fail2ban/fail2ban/tree/master/config/filter.d)

## 14. Backup — rclone to SharePoint

### Configure rclone for SharePoint

```bash
sudo -u promptgrimoire rclone config
```

Follow the interactive setup:
1. Choose `n` for new remote
2. Name it `sharepoint`
3. Select `onedrive` (type number varies by version — search for it)
4. Enter your Microsoft 365 client ID and secret (create an app registration in Azure AD if needed)
5. Select `sharepoint` as the drive type
6. Authenticate via browser (use `--auth-no-open-browser` on a headless server and paste the URL locally)
7. Select the target SharePoint site and document library

> **Ref:** [rclone OneDrive/SharePoint setup](https://rclone.org/onedrive/), [rclone config](https://rclone.org/commands/rclone_config/)

### Backup script

Create `/usr/local/bin/promptgrimoire-backup`:

```bash
#!/bin/bash
# Nightly backup of PromptGrimoire database and config to SharePoint.
# Expected restore time: ~1 day (rebuild VM from deployment guide + restore DB).
#
# Ref: https://www.postgresql.org/docs/16/app-pgdump.html
# Ref: https://rclone.org/commands/rclone_copy/
set -euo pipefail

BACKUP_DIR="/var/backups/promptgrimoire"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REMOTE="sharepoint:PromptGrimoire/backups"
RCLONE_CONFIG="/home/promptgrimoire/.config/rclone/rclone.conf"
RETAIN_DAYS=30

mkdir -p "$BACKUP_DIR"

# 1. Database dump (custom format for pg_restore)
sudo -u postgres pg_dump -Fc promptgrimoire \
  > "${BACKUP_DIR}/db-${TIMESTAMP}.dump"

# 2. App config (secrets — handle with care)
cp /opt/promptgrimoire/.env "${BACKUP_DIR}/env-${TIMESTAMP}"
chmod 600 "${BACKUP_DIR}/env-${TIMESTAMP}"

# 3. Compress
tar czf "${BACKUP_DIR}/promptgrimoire-${TIMESTAMP}.tar.gz" \
  -C "$BACKUP_DIR" \
  "db-${TIMESTAMP}.dump" \
  "env-${TIMESTAMP}"

# 4. Upload to SharePoint
rclone --config "$RCLONE_CONFIG" copy \
  "${BACKUP_DIR}/promptgrimoire-${TIMESTAMP}.tar.gz" "$REMOTE/" \
  --log-level INFO

# 5. Clean up local files
rm -f "${BACKUP_DIR}/db-${TIMESTAMP}.dump" "${BACKUP_DIR}/env-${TIMESTAMP}"
find "$BACKUP_DIR" -name "promptgrimoire-*.tar.gz" -mtime +${RETAIN_DAYS} -delete

echo "Backup complete: promptgrimoire-${TIMESTAMP}.tar.gz -> ${REMOTE}/"
```

```bash
sudo chmod +x /usr/local/bin/promptgrimoire-backup

# Test it
sudo /usr/local/bin/promptgrimoire-backup
```

### Cron job (nightly at 3am)

```bash
echo '0 3 * * * root /usr/local/bin/promptgrimoire-backup >> /var/log/promptgrimoire-backup.log 2>&1' \
  | sudo tee /etc/cron.d/promptgrimoire-backup
```

### Restore procedure

```bash
# 1. Download the backup from SharePoint
rclone --config /home/promptgrimoire/.config/rclone/rclone.conf \
  copy "sharepoint:PromptGrimoire/backups/promptgrimoire-YYYYMMDD-HHMMSS.tar.gz" /tmp/

# 2. Extract
cd /tmp && tar xzf promptgrimoire-*.tar.gz

# 3. Restore database
sudo -u postgres pg_restore -d promptgrimoire --clean --if-exists /tmp/db-*.dump

# 4. Restore .env
sudo cp /tmp/env-* /opt/promptgrimoire/.env
sudo chown promptgrimoire:promptgrimoire /opt/promptgrimoire/.env

# 5. Restart app
sudo systemctl restart promptgrimoire
```

> **Ref:** [pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html), [rclone copy](https://rclone.org/commands/rclone_copy/)

## 15. Verify Everything

```bash
# Services
sudo systemctl status postgresql
sudo systemctl status promptgrimoire
sudo systemctl status haproxy
sudo systemctl status fail2ban

# App responds (NiceGUI doesn't support HEAD, so use GET and check status code)
curl -s -o /dev/null -w "%{http_code}" https://grimoire.drbbs.org

# TLS certificate
echo | openssl s_client -connect grimoire.drbbs.org:443 -servername grimoire.drbbs.org 2>/dev/null \
  | openssl x509 -noout -dates

# WebSocket (open in browser, check Network tab for wss:// upgrade)

# Firewall
sudo ufw status verbose

# fail2ban jails
sudo fail2ban-client status sshd

# Certbot auto-renewal
sudo certbot renew --dry-run

# Backup
sudo /usr/local/bin/promptgrimoire-backup
```

---

## Ongoing Operations

All `manage-users` commands below use the `grimoire-run` helper (installed in Step 8).

### Create a unit and add an instructor

1. **Create the unit** — log in as admin at `https://grimoire.drbbs.org/courses/new`. Fill in unit code (e.g. `LAWS1100`), name, semester (e.g. `2026-S1`). You are auto-enrolled as coordinator.

2. **Enrol your colleague** — they must have logged in at least once (AAF/magic link auto-creates their account). Then:

```bash
grimoire-run manage-users enroll colleague@mq.edu.au LAWS1100 2026-S1 --role instructor
```

3. **Grant Stytch instructor role** — this gives org-level privilege (copy-protection bypass, `is_privileged_user()` = true):

```bash
grimoire-run manage-users instructor colleague@mq.edu.au
```

Step 2 is the *course-level* role (can manage weeks, activities, settings for that unit). Step 3 is the *org-level* Stytch role (bypasses copy protection globally, sees all workspaces as owner). Both are needed for full instructor access.

### User management

```bash
# List all users who have logged in
grimoire-run manage-users list

# List all users including pre-created
grimoire-run manage-users list --all

# Show a user's details and enrollments
grimoire-run manage-users show colleague@mq.edu.au

# Pre-create a user (before they've logged in)
grimoire-run manage-users create colleague@mq.edu.au --name "Jane Smith"

# Grant/revoke org-level admin
grimoire-run manage-users admin colleague@mq.edu.au
grimoire-run manage-users admin colleague@mq.edu.au --remove

# Grant/revoke Stytch instructor role
grimoire-run manage-users instructor colleague@mq.edu.au
grimoire-run manage-users instructor colleague@mq.edu.au --remove

# Change a user's course role
grimoire-run manage-users role colleague@mq.edu.au LAWS1100 2026-S1 coordinator

# Remove a user from a course
grimoire-run manage-users unenroll colleague@mq.edu.au LAWS1100 2026-S1
```

**Available course roles** (in ascending privilege): `student`, `tutor`, `instructor`, `coordinator`. Roles marked `is_staff` (`instructor`, `coordinator`) can see unpublished weeks, manage activities, and edit locked tags.

### Role model

Three independent layers determine what a user can do:

| Layer | Scope | Grants | Set via |
|-------|-------|--------|---------|
| **Org admin** | Global | Owner of all workspaces, bypasses all ACLs | `manage-users admin` |
| **Stytch instructor** | Global | `is_privileged_user()` = true, bypasses copy protection | `manage-users instructor` (or AAF `eduperson_affiliation=staff`) |
| **Course role** | Per-unit | `student`/`tutor`/`instructor`/`coordinator` — controls week visibility, activity settings, tag locks | `manage-users enroll --role` or `manage-users role` |

A user typically needs both a **course role** (to see the unit's content) and the **Stytch instructor role** (for global privileges). Org admin is reserved for you.

### Course and activity settings (UI)

All course/activity configuration is done through the web UI:

- **Unit settings** — click the settings icon on the course page. Controls defaults for copy protection, sharing, anonymous sharing, and tag creation.
- **Week management** — create weeks, publish/unpublish (students only see published weeks).
- **Activity settings** — per-activity overrides using tri-state (on/off/inherit from unit). Controls copy protection, sharing, tag creation, and anonymity.
- **Tag management** — open from any workspace's annotation page. Create/edit tag groups and tags, import from CSV/JSON, lock tags (students can't modify locked tags), drag-reorder.

### Deploy an update

```bash
cd /opt/promptgrimoire
sudo -u promptgrimoire git pull
sudo -u promptgrimoire /home/promptgrimoire/.local/bin/uv sync --no-dev
sudo systemctl restart promptgrimoire
```

Alembic migrations run automatically on app start.

### View logs

```bash
# App (systemd journal)
sudo journalctl -u promptgrimoire -f

# App (file logs, more detail)
ls /opt/promptgrimoire/logs/

# HAProxy
sudo tail -f /var/log/haproxy.log

# fail2ban
sudo tail -f /var/log/fail2ban.log

# Backup
sudo tail -f /var/log/promptgrimoire-backup.log
```

### Health checks

```bash
# All services running?
sudo systemctl status postgresql promptgrimoire haproxy fail2ban

# App responds? (NiceGUI doesn't support HEAD — use GET)
curl -s -o /dev/null -w "%{http_code}" https://grimoire.drbbs.org

# TLS certificate valid?
echo | openssl s_client -connect grimoire.drbbs.org:443 -servername grimoire.drbbs.org 2>/dev/null \
  | openssl x509 -noout -dates

# Database?
sudo -u promptgrimoire psql -d promptgrimoire -c "SELECT 1;"

# Certbot auto-renewal?
sudo certbot renew --dry-run

# fail2ban jails?
sudo fail2ban-client status
```

### Unban an IP

```bash
sudo fail2ban-client set sshd unbanip <ip>
sudo fail2ban-client set haproxy-http-flood unbanip <ip>
```

### Seed development data

For dev/test environments only — creates mock users, a LAWS1100 course, weeks, activities, and a legal case brief tag template:

```bash
grimoire-run seed-data
```

Idempotent — safe to run multiple times.

---

## Quick Reference

| What | Where |
|------|-------|
| `grimoire-run` helper | `/usr/local/bin/grimoire-run` |
| App source | `/opt/promptgrimoire/` |
| App config | `/opt/promptgrimoire/.env` |
| App logs | `/opt/promptgrimoire/logs/` + `journalctl -u promptgrimoire` |
| Deploy key | `/home/promptgrimoire/.ssh/id_ed25519` |
| systemd unit | `/etc/systemd/system/promptgrimoire.service` |
| HAProxy config | `/etc/haproxy/haproxy.cfg` |
| HAProxy combined cert | `/etc/haproxy/certs/grimoire.drbbs.org.pem` |
| Let's Encrypt certs | `/etc/letsencrypt/live/grimoire.drbbs.org/` |
| Cert smush script | `/usr/local/bin/haproxy-cert-smush` |
| Certbot deploy hook | `/etc/letsencrypt/renewal-hooks/deploy/50-haproxy.sh` |
| Certbot renewal config | `/etc/letsencrypt/renewal/grimoire.drbbs.org.conf` |
| fail2ban config | `/etc/fail2ban/jail.local` |
| PostgreSQL data | `/var/lib/postgresql/` (default) |
| TinyTeX | `/home/promptgrimoire/.TinyTeX/` |
| Backup script | `/usr/local/bin/promptgrimoire-backup` |
| Backup log | `/var/log/promptgrimoire-backup.log` |
| Local backup staging | `/var/backups/promptgrimoire/` |
| SharePoint backup | `sharepoint:PromptGrimoire/backups/` |

## Known Limitations

- **Hot reload** is on by default (`PROMPTGRIMOIRE_RELOAD=1`). `run_prod.py` disables it. `run.py` (dev) keeps it.
- **Single process.** NiceGUI + uvicorn handles connections asynchronously. No horizontal scaling. Fine for 30-60 concurrent students.
- **PDF export blocks briefly.** LaTeX compilation is CPU-bound. Under heavy concurrent export load, consider `asyncio.to_thread()` wrapping (tracked in perf epic #142).
- **Initial cert only uses port 80 standalone.** The first `certbot certonly --standalone` requires port 80 free (HAProxy not yet running). All subsequent renewals use standalone on port 8402 behind HAProxy with zero downtime.

## Sources

| Topic | Reference |
|-------|-----------|
| HAProxy WebSocket | https://www.haproxy.com/documentation/haproxy-configuration-tutorials/protocol-support/websocket/ |
| HAProxy SSL termination | https://www.haproxy.com/blog/haproxy-ssl-termination |
| HAProxy timeouts | https://www.haproxy.com/blog/the-four-essential-sections-of-an-haproxy-configuration |
| certbot standalone plugin | https://eff-certbot.readthedocs.io/en/stable/using.html#standalone |
| certbot deploy hooks | https://eff-certbot.readthedocs.io/en/stable/using.html#pre-and-post-validation-hooks |
| Let's Encrypt HTTP-01 | https://letsencrypt.org/docs/challenge-types/#http-01-challenge |
| fail2ban | https://www.fail2ban.org/wiki/index.php/MANUAL_0_8 |
| UFW | https://manpages.ubuntu.com/manpages/noble/en/man8/ufw.8.html |
| unattended-upgrades | https://documentation.ubuntu.com/server/how-to/software/automatic-updates/ |
| OpenSSH hardening | https://man.openbsd.org/sshd_config |
| PostgreSQL pg_dump | https://www.postgresql.org/docs/16/app-pgdump.html |
| pg_restore | https://www.postgresql.org/docs/16/app-pgrestore.html |
| rclone SharePoint | https://rclone.org/onedrive/ |
| systemd sandboxing | https://www.freedesktop.org/software/systemd/man/systemd.exec.html#Sandboxing |
| uv installation | https://docs.astral.sh/uv/getting-started/installation/ |
| uv Python management | https://docs.astral.sh/uv/guides/install-python/ |
| python-build-standalone | https://github.com/astral-sh/python-build-standalone |
| TinyTeX | https://yihui.org/tinytex/ |
| GitHub deploy keys | https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#deploy-keys |
| fio disk benchmark | https://fio.readthedocs.io/en/latest/ |
| Ghostty terminfo | https://ghostty.org/docs/help/terminfo |
| AAF OIDC integration | https://tutorials.aaf.edu.au/openid-connect-integration |
| AAF Federation Manager | https://manager.aaf.edu.au/ |
| AAF test federation | https://manager.test.aaf.edu.au/ |
| Stytch B2B SSO | https://stytch.com/docs/b2b/guides/sso/overview |
| Stytch OAuth | https://stytch.com/docs/b2b/guides/oauth/overview |
| Google Cloud OAuth | https://console.cloud.google.com/apis/credentials |
