# Deployment Guide — PromptGrimoire

*Last updated: 2026-08-15*
*Target: DigitalOcean — Ubuntu 24.04 LTS, 8 vCPU / 32 GB RAM, 400 GB SSD, SYD1, grimoire.drbbs.org*
*Previous: NCI Cloud VM — 4 vCPU / 8 GB RAM, 60 GB Cinder volume*

## Architecture Overview

```
                        ┌─────────────────────┐
┌─────────┐             │      HAProxy        │
│ Browser  │────────────▶│  :80 → 301 → :443  │
│ (HTTPS)  │◀────────────│  :443 TLS terminate │
└─────────┘             └─────────┬───────────┘
                                  │
                        ┌─────────▼───────────┐
                        │   promptgrimoire    │────────────┐
                        │   :8080 (uvicorn)   │            │
                        │   search_worker     │            │
                        │   (asyncio task)    │            │
                        └─────────────────────┘            │
                                                         ▼
                        ┌─────────────────────┐      ┌────────────┐      ┌────────────┐
                        │ export worker       │─────▶│ PgBouncer  │─────▶│ PostgreSQL │
                        │ (systemd service)   │      │   :6432    │      │   :5432    │
                        └─────────────────────┘      └────────────┘      └────────────┘
                                                     ┌────────────┐
                                                     │ External   │
                                                     │ - Stytch   │
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

NiceGUI runs on uvicorn and the search worker remains an internal asyncio task. Production runs PDF compilation in the separate `promptgrimoire-worker.service` (`FEATURES__WORKER_IN_PROCESS=false`). Both processes share QueuePool configuration through PgBouncer; `DATABASE__USE_NULL_POOL=false` is intentional on this topology.

**Recovery time objective:** ~1 day (rebuild VM from this guide + restore DB from SharePoint backup).

---

## 0. DigitalOcean Droplet Setup

Provision the production host in the DigitalOcean control panel.

- **Image:** Ubuntu 24.04 LTS
- **Region:** Sydney (`SYD1`)
- **Current capacity:** 8 vCPU, 32 GB RAM, 400 GB local SSD
- **Authentication:** SSH key; do not enable password login
- **Tag:** attach a production tag and use it to target the Cloud Firewall
- **Cloud Firewall:** allow inbound TCP 22 from administrative source addresses
  where practical, plus public TCP 80 and 443; allow required outbound traffic
- **Backups:** enable DigitalOcean backups as a host-level recovery layer; the
  application-aware nightly backup in Step 14 remains mandatory

Do not assume a Linux device name from this document. Verify the provisioned
machine and root filesystem before installing data services:

```bash
nproc
free -h
findmnt -no SOURCE,SIZE,FSTYPE,TARGET /
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
```

**Swap:** Keep a 2 GB swapfile as an emergency buffer so a memory spike is less
likely to make SSH unavailable (see the
[2026-03-15 post-mortem](postmortems/2026-03-15-production-oom.md)).

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

```bash
ssh root@<droplet-ip>
```

Create a non-root sudo operator before disabling root SSH. The remaining
commands assume that operator account. Point the `grimoire.drbbs.org` A record
to the Droplet's public or reserved IP. Certbot (Step 12) requires DNS to
resolve first.

**Terminal:** If using Ghostty, copy the terminfo to the server before doing anything else. The remote won't have the `xterm-ghostty` entry, and byobu/tmux/ncurses tools will break without it.

```bash
# From your LOCAL machine (not the server)
infocmp -x xterm-ghostty | ssh <operator>@grimoire.drbbs.org 'tic -x -'
```

Verify after SSH-ing in: `echo $TERM` should show `xterm-ghostty` and `tput colors` should return `256`.

> **Ref:** [DigitalOcean recommended Droplet
> setup](https://docs.digitalocean.com/products/droplets/getting-started/recommended-droplet-setup/),
> [DigitalOcean backups](https://docs.digitalocean.com/products/backups/),
> [Ghostty terminfo](https://ghostty.org/docs/help/terminfo)

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
  poppler-utils \
  pngquant \
  curl \
  fio \
  ioping \
  jq \
  socat \
  bats \
  fontconfig \
  mecab libmecab-dev
```

Install the current Node.js 22 LTS line and an npm release new enough to enforce
the repository's `min-release-age` policy. Node and npm are deployment/test
tools; the application does not run on Node:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install --global npm@11.10.0
node --version
npm --version
bats --version
```

### MeCab (word count)

`mecab` and `libmecab-dev` provide the C library and headers for Japanese word segmentation (used by `mecab-python3`). The Python dictionary (`unidic-lite`) is installed automatically by `uv sync`. Two failure modes at app startup:

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ImportError: MeCab is required for Japanese word counting` | `libmecab.so` not on system | `apt install mecab libmecab-dev` |
| `RuntimeError: MeCab is installed but could not be initialised` | Library present but no dictionary found | `uv sync` (installs `unidic-lite`) or `apt install mecab-ipadic-utf8` |

Both errors appear in `journalctl -u promptgrimoire` at startup and prevent the app from loading.

```bash
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

The DigitalOcean Cloud Firewall provides the outer policy; UFW provides
host-level defence in depth.

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

All current production data lives on the Droplet's 400 GB root SSD. Benchmark
the filesystem mounted at `/` before configuring PostgreSQL; do not assume its
device name.

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

Record these numbers — they feed into PostgreSQL tuning in Step 7.

| Metric | NCI Cinder (4 vCPU / 8 GB) | DO SSD (8 vCPU / 32 GB) |
|--------|---------------------------|--------------------------|
| Sequential write | ~100–200 MB/s | not benchmarked |
| Random 4K IOPS | ~5k–10k | ~19.5k |
| Read latency (4K) | ~0.5–2 ms | ~354 µs |
| Write latency (4K) | — | ~10 µs |

*DO benchmarks recorded 2026-03-28 during migration.*

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

Set a safety net for connection leaks — any connection idle in a transaction for more than 60 seconds is terminated by PostgreSQL. This prevents a leaked session from exhausting the connection pool and taking down the app. Set this **globally** (not just per-database) so it catches any connection.

```bash
sudo -u postgres psql -c "ALTER SYSTEM SET idle_in_transaction_session_timeout = '60s';"
sudo -u postgres psql -c "ALTER SYSTEM SET statement_timeout = '30s';"
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

These settings are reload-settable — `pg_reload_conf()` activates them immediately without a restart. The performance tuning section below includes a full restart (needed for `shared_buffers` and `max_connections`), which also picks up these settings.

> **Incident (2026-03-24):** A deploy leaked sessions that sat idle-in-transaction indefinitely, exhausting the pool (69/80 checked out) and causing 60s timeouts on all page loads. The per-database `ALTER DATABASE ... SET` was in place but `SHOW idle_in_transaction_session_timeout` returned `0` outside the database context — `ALTER SYSTEM` ensures the setting applies globally.

### Performance tuning

The default PostgreSQL configuration is tuned for compatibility, not performance. These settings are critical for an SSD-backed OLTP workload serving 500+ concurrent users. Values below are for the **DO deployment (8 vCPU / 32 GB RAM)**; NCI values (4 vCPU / 8 GB) are shown for reference.

```bash
sudo -u postgres psql <<'SQL'
-- Memory: 25% of RAM for shared_buffers, 50% for effective_cache_size
ALTER SYSTEM SET shared_buffers = '8GB';
ALTER SYSTEM SET effective_cache_size = '16GB';
ALTER SYSTEM SET work_mem = '12MB';
ALTER SYSTEM SET maintenance_work_mem = '2GB';

-- Large shared_buffers benefit from huge pages (reduces TLB misses)
ALTER SYSTEM SET huge_pages = 'try';

-- JIT compilation adds overhead for short OLTP queries
ALTER SYSTEM SET jit = 'off';

-- SSD: random reads are nearly as fast as sequential
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;

-- WAL: spread checkpoint I/O, reduce frequency
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET max_wal_size = '2GB';
ALTER SYSTEM SET min_wal_size = '512MB';
ALTER SYSTEM SET wal_buffers = '16MB';

-- Connections: sized for PgBouncer (Step 7a) + worker + reserves
ALTER SYSTEM SET max_connections = 120;

-- Slow query logging (queries > 1s)
ALTER SYSTEM SET log_min_duration_statement = 1000;
SQL
```

Restart PostgreSQL to apply (`shared_buffers`, `max_connections`, `huge_pages` require restart):

```bash
sudo systemctl restart postgresql
```

Verify non-default settings:

```bash
sudo -u postgres psql -c "SELECT name, setting, source FROM pg_settings WHERE source = 'override' ORDER BY name;"
```

| Setting | Default | NCI (8 GB) | DO (32 GB) | Why |
|---------|---------|------------|------------|-----|
| `shared_buffers` | 128 MB | 2 GB | 8 GB | 25% of RAM; entire DB fits in cache |
| `effective_cache_size` | 4 GB | 6 GB | 16 GB | 50% of RAM; tells planner to prefer index scans |
| `work_mem` | 4 MB | 16 MB | 12 MB | Per-operation memory; lower is safer under high concurrency (work_mem × ops can blow out RAM) |
| `maintenance_work_mem` | 64 MB | — | 2 GB | ~6% of RAM; faster VACUUM and index rebuilds |
| `huge_pages` | `try` | — | `try` | Reduces TLB misses with large shared_buffers |
| `jit` | `on` | — | `off` | JIT overhead hurts short OLTP queries more than it helps |
| `random_page_cost` | 4.0 | 1.1 | 1.1 | Default assumes spinning disk; SSD random ≈ sequential |
| `effective_io_concurrency` | 1 | 200 | 200 | SSD can service many parallel reads |
| `checkpoint_completion_target` | 0.5 | 0.9 | 0.9 | Spreads checkpoint I/O over 90% of interval, less spike |
| `max_wal_size` | 1 GB | 2 GB | 2 GB | Reduces checkpoint frequency |
| `max_connections` | 100 | 120 | 120 | 80 from PgBouncer + worker + vacuum + backup + psql |
| `statement_timeout` | 0 | 30s | 30s | Kills runaway queries; override per-session for long jobs |
| `log_min_duration_statement` | -1 | 1000ms | 1000ms | Logs slow queries for diagnosis |

> **Ref:** [PostgreSQL 16 resource consumption](https://www.postgresql.org/docs/16/runtime-config-resource.html), [PostgreSQL 16 WAL configuration](https://www.postgresql.org/docs/16/wal-configuration.html), [PostgreSQL wiki: tuning](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server), [pgtune](https://pgtune.leopard.in.ua/)

The `promptgrimoire` system user (created in Step 8) authenticates via `peer` — no password needed for local Unix socket connections. Peer auth verification:

```bash
# Run this AFTER Step 8 (service user must exist first)
sudo -u promptgrimoire psql -d promptgrimoire -c "SELECT 1;"
```

> **Ref:** [PostgreSQL 16 createuser](https://www.postgresql.org/docs/16/app-createuser.html), [pg_hba.conf auth methods](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html)

## 7a. PgBouncer

PgBouncer is a lightweight connection pooler that sits between the application and PostgreSQL. It queues connection requests during bursts (preventing pool exhaustion) and multiplexes many client connections over fewer real PostgreSQL connections.

> **Incident (2026-03-24):** Without PgBouncer, a thundering herd after deploy restart filled the 80-connection pool with idle-in-transaction sessions. PgBouncer's queuing breaks the retry amplification loop — failed connections queue instead of generating new retries.

```bash
sudo apt install pgbouncer
```

### Run PgBouncer as the application user

The Debian package runs PgBouncer as `postgres` by default. PostgreSQL uses `peer` auth (OS user must match PG role), so PgBouncer must run as the `promptgrimoire` system user for peer auth to work. Override the systemd unit:

```bash
sudo systemctl edit pgbouncer
```

Add:

```ini
[Service]
User=promptgrimoire
Group=promptgrimoire
RuntimeDirectory=pgbouncer
RuntimeDirectoryMode=0750
PIDFile=/run/pgbouncer/pgbouncer.pid
```

`RuntimeDirectory=pgbouncer` tells systemd to create `/run/pgbouncer/` with correct ownership automatically and clean it up on shutdown. This avoids permission issues with `/var/run/postgresql/` (owned by `postgres`).

Create the log directory:

```bash
sudo mkdir -p /var/log/pgbouncer
sudo chown promptgrimoire:promptgrimoire /var/log/pgbouncer
```

> **Ref:** [PgBouncer systemd service](https://github.com/pgbouncer/pgbouncer/blob/master/etc/pgbouncer.service), [EDB: running multiple PgBouncer instances with systemd](https://www.enterprisedb.com/blog/running-multiple-pgbouncer-instances-systemd)

### Configure PgBouncer

Edit `/etc/pgbouncer/pgbouncer.ini`:

```ini
[databases]
promptgrimoire = host=/var/run/postgresql port=5432 dbname=promptgrimoire
; Bootstrap needs the postgres maintenance database for ensure_database_exists()
postgres = host=/var/run/postgresql port=5432 dbname=postgres

[pgbouncer]
; Listen on Unix socket only — no network exposure.
; Socket lives in /run/pgbouncer/ (managed by systemd RuntimeDirectory).
listen_addr =
listen_port = 6432
unix_socket_dir = /run/pgbouncer

; Transaction pooling: connection returned to pool after each transaction
pool_mode = transaction

; Client-facing limits (app + worker + admin)
max_client_conn = 500
default_pool_size = 40
reserve_pool_size = 10
reserve_pool_timeout = 3

; Prepared statement support (PgBouncer 1.21+)
; Intercepts PREPARE commands and maintains LRU cache per server connection.
; asyncpg prepared statements work transparently — no code changes needed.
max_prepared_statements = 200

; Auth: trust on Unix socket (no network exposure).
; auth_file is required even with trust — PgBouncer must know valid users.
auth_type = trust
auth_file = /etc/pgbouncer/userlist.txt

; Timeouts
server_lifetime = 3600
server_idle_timeout = 600
client_login_timeout = 15

; Admin access for SHOW POOLS/STATS monitoring
admin_users = promptgrimoire
stats_users = promptgrimoire

; Logging and PID (paths match systemd RuntimeDirectory)
logfile = /var/log/pgbouncer/pgbouncer.log
pidfile = /run/pgbouncer/pgbouncer.pid
```

Set file ownership and register the application user:

```bash
sudo chown promptgrimoire:promptgrimoire /etc/pgbouncer/pgbouncer.ini /etc/pgbouncer/userlist.txt
echo '"promptgrimoire" ""' | sudo tee /etc/pgbouncer/userlist.txt
```

PgBouncer runs as `promptgrimoire` and connects to PostgreSQL via Unix socket. PostgreSQL's `peer` auth sees OS user `promptgrimoire` matching PG role `promptgrimoire` — no password, no `pg_hba.conf` changes needed.

> **Ref:** [PgBouncer configuration](https://www.pgbouncer.org/config.html), [PgBouncer 1.21 prepared statement support](https://www.postgresql.org/about/news/pgbouncer-1210-released-now-with-prepared-statements-2735/), [PgBouncer auth file format](https://www.pgbouncer.org/config.html#auth_file)

### Start and enable

```bash
sudo systemctl daemon-reload
sudo systemctl enable pgbouncer
sudo systemctl start pgbouncer

# Verify: connect through PgBouncer
sudo -u promptgrimoire psql -h /run/pgbouncer -p 6432 -d promptgrimoire -c "SELECT 1;"
```

### Monitoring

Connect to PgBouncer's admin console to check pool health:

```bash
sudo -u promptgrimoire psql -h /run/pgbouncer -p 6432 -d pgbouncer
```

```sql
-- Pool status: cl_active (busy clients), cl_waiting (queued), sv_active (busy PG conns)
SHOW POOLS;

-- Aggregate statistics
SHOW STATS;

-- Connected clients
SHOW CLIENTS;

-- Reload config without dropping connections
RELOAD;
```

**Key health indicators:**
- `cl_waiting > 0` sustained → increase `default_pool_size` (currently 40)
- `sv_active = default_pool_size` sustained → pool saturated, check for slow queries

> **Ref:** [PgBouncer usage (SHOW commands)](https://www.pgbouncer.org/usage.html)

### Connection pooling behind PgBouncer

Production uses **QueuePool** (SQLAlchemy's default) behind PgBouncer in transaction mode. The pool is deliberately undersized relative to PgBouncer's `default_pool_size` to avoid the double-pooling bottleneck where SQLAlchemy queues while PgBouncer has spare capacity.

```bash
DATABASE__USE_NULL_POOL=false
DATABASE__POOL_SIZE=20
DATABASE__MAX_OVERFLOW=10
DATABASE__POOL_PRE_PING=false
DATABASE__POOL_RECYCLE=1800
```

- **`POOL_PRE_PING=false`**: Disabled because `pool_pre_ping=True` + PgBouncer transaction mode can cause `unnamed prepared statement` errors when PgBouncer reassigns the server connection between ping and query (SQLAlchemy #10226). PgBouncer handles connection health.
- **`POOL_RECYCLE=1800`**: Shorter than PgBouncer's `server_lifetime` (3600s) to prevent stale connection errors.
- **`POOL_SIZE=20` + `MAX_OVERFLOW=10`**: At most 30 concurrent connections through PgBouncer. `default_pool_size=40` provides headroom.

**History:** Production initially used `NullPool` (every query creates/destroys a connection) to avoid double-pooling. Telemetry from 2026-03-30 showed NullPool caused ~8,400 PgBouncer connection cycles/hour, 629 connection close errors/34h, and 60 login timeouts/49h. QueuePool(20) deployed 2026-03-30 to reduce connection churn. See `docs/design-plans/2026-03-30-db-pool-configuration.md` for the full analysis.

In development (direct PostgreSQL, no PgBouncer), the default pool settings are fine — no `.env` override needed.

> **Ref:** [SQLAlchemy pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html), [PgBouncer FAQ](https://www.pgbouncer.org/faq.html), [SQLAlchemy #10226](https://github.com/sqlalchemy/sqlalchemy/issues/10226)

## 7b. Streaming Replication

PostgreSQL streaming replication sends WAL (write-ahead log) records from a primary server to a standby in near-real-time, maintaining a hot standby that can be promoted if the primary fails.

### Primary-side configuration (DO)

**postgresql.conf on DO primary:**

```ini
# Streaming replication (§ 7b)
wal_level = replica                    # Required for streaming replication (NOT default)
max_wal_senders = 5                    # 1 standby + headroom for reconnection + pg_basebackup
wal_keep_size = 256MB                  # Retain WAL segments as fallback
max_replication_slots = 2              # 1 active + 1 spare
```

After changing `wal_level`, restart PostgreSQL (`sudo systemctl restart postgresql@16-main`). The other parameters only require a reload.

**Replication user:**

```sql
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD '<strong_password>';
```

Store the password securely — it will be needed in the standby's `primary_conninfo`.

**pg_hba.conf entry:**

```
# Streaming replication from NCI standby (§ 7b)
hostssl  replication  replicator  <NCI_PUBLIC_IP>/32  scram-sha-256
```

Reload after editing: `sudo -u postgres psql -c 'SELECT pg_reload_conf();'`

**Replication slot with bounded WAL retention:**

```sql
SELECT pg_create_physical_replication_slot('nci_standby');
-- Prevent unbounded WAL accumulation if standby goes offline
ALTER SYSTEM SET max_slot_wal_keep_size = '1GB';
SELECT pg_reload_conf();
```

The `max_slot_wal_keep_size` limit ensures that if the standby is offline for an extended period, WAL files do not fill the primary's disk. If the slot falls behind this limit, the standby must be re-bootstrapped with `pg_basebackup`.

> **Ref:** [PostgreSQL 16 WAL Configuration](https://www.postgresql.org/docs/16/runtime-config-replication.html), [Replication Slots](https://www.postgresql.org/docs/16/warm-standby.html#STREAMING-REPLICATION-SLOTS)

### Standby configuration and bootstrap (NCI)

**Initial bootstrap (run on NCI standby):**

```bash
# Stop PostgreSQL on standby
sudo systemctl stop postgresql@16-main

# Clear existing data directory
sudo -u postgres rm -rf /var/lib/postgresql/16/main/*

# Take base backup from primary (-R creates standby.signal and connection config)
# Use a dedicated PostgreSQL hostname covered by the server certificate
# (for example `db-primary.grimoire.drbbs.org`), not a raw IP, because
# sslmode=verify-full checks the certificate name against the host value.
sudo -u postgres pg_basebackup \
  -h <DO_PRIMARY_HOSTNAME> \
  -U replicator \
  -D /var/lib/postgresql/16/main \
  -Fp -Xs -P -R \
  -S nci_standby

# Verify standby.signal was created
ls -la /var/lib/postgresql/16/main/standby.signal

# Start PostgreSQL (will begin streaming)
sudo systemctl start postgresql@16-main
```

The `-R` flag tells `pg_basebackup` to create `standby.signal` and write connection settings to `postgresql.auto.conf`. The `-S nci_standby` flag binds the standby to the replication slot created on the primary, ensuring WAL retention even if the standby disconnects temporarily.

`sslmode=verify-full` requires hostname validation. Do not use the DO public IP here unless the PostgreSQL server certificate includes that IP in its Subject Alternative Name. The recommended setup is a dedicated DNS name such as `db-primary.grimoire.drbbs.org` that resolves to the DO primary and is covered by the certificate. If you cannot provision a hostname-backed certificate yet, explicitly downgrade to `sslmode=verify-ca` and document that deviation.

**Standby postgresql.conf (auto-created by `-R`, verify these exist in `postgresql.auto.conf`):**

```ini
primary_conninfo = 'host=<DO_PRIMARY_HOSTNAME> port=5432 user=replicator password=<password> application_name=nci_standby sslmode=verify-full sslrootcert=/etc/ssl/certs/ca-certificates.crt'
primary_slot_name = 'nci_standby'
recovery_target_timeline = 'latest'
```

**Verification query (run on primary):**

```sql
SELECT pid, usename, application_name, state, sync_state,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

Expected: `state = 'streaming'`, `application_name = 'nci_standby'`.

Note: `pg_stat_replication` does not have a `slot_name` column in PostgreSQL 16. The standby is identified by `application_name`, which is set via `primary_conninfo` (defaults to `walreceiver` unless overridden). To include the standby's application name, add `application_name=nci_standby` to `primary_conninfo`.

If the standby has been offline long enough that WAL was reclaimed (beyond `max_slot_wal_keep_size`), the replication slot becomes invalidated. In that case, drop and recreate the slot on the primary, then re-run the full `pg_basebackup` bootstrap above.

### Manual failover procedure

Automated failover is explicitly out of scope — over-engineering for a megs-sized DB with nightly backups. This is a manual procedure for when the DO primary is lost or being decommissioned.

**1. Verify standby is caught up:**

```sql
-- On primary (if still accessible)
SELECT pg_current_wal_lsn();

-- On standby
SELECT pg_last_wal_replay_lsn();
```

Both should match (or be very close). If the primary is down, skip this step — the standby will replay whatever WAL it has received.

**2. Stop the primary** (or it's already down):

```bash
sudo systemctl stop postgresql@16-main
```

**3. Promote the standby:**

```sql
-- On NCI standby
SELECT pg_promote();
```

Or via command line: `sudo -u postgres pg_ctl promote -D /var/lib/postgresql/16/main`

The `standby.signal` file is removed automatically on promotion. The standby becomes a read-write primary.

**4. Keep the application topology unchanged (PgBouncer stays in path):**

Production normally connects through the local PgBouncer socket:

```bash
# DATABASE__URL should continue to use the local PgBouncer socket:
#   DATABASE__URL=postgresql+asyncpg://promptgrimoire@/promptgrimoire?host=/run/pgbouncer&port=6432

# PgBouncer on NCI should point at the local PostgreSQL socket:
#   promptgrimoire = host=/var/run/postgresql port=5432 dbname=promptgrimoire

# If PgBouncer was stopped on NCI, start or restart it first
sudo systemctl restart pgbouncer

# Then restart the app and worker
sudo systemctl restart promptgrimoire promptgrimoire-worker
```

No `DATABASE__URL` change is needed if NCI already uses the standard production topology from Section 7a. Only bypass PgBouncer temporarily for diagnostics or migrations.

If the app was running on the DO host, stop it there first:
```bash
# On DO (if accessible)
sudo systemctl stop promptgrimoire promptgrimoire-worker
```

**5. Update DNS:**

Point `grimoire.drbbs.org` A record to NCI's public IP. The old DO IP should stop serving traffic once the app is stopped there.

**6. Verify:**

```bash
curl https://grimoire.drbbs.org/healthz
```

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

# Install the exact initial environment at a stable commit-keyed path. Virtual
# environment entry points embed this path, while .venv is the selected-release
# symlink used by uv and systemd.
initial_commit=$(sudo -u promptgrimoire git rev-parse HEAD)
sudo -u promptgrimoire mkdir -p .venvs
sudo -u promptgrimoire env UV_PROJECT_ENVIRONMENT=".venvs/$initial_commit" \
  /home/promptgrimoire/.local/bin/uv sync --locked
sudo -u promptgrimoire ln -s ".venvs/$initial_commit" .venv

# Create .env from template
sudo -u promptgrimoire cp .env.example .env
```

The supply-chain cooldown is project-owned: `pyproject.toml` configures uv's
`exclude-newer = "14 days"`, and `.npmrc` carries the corresponding npm
policy. Nothing is copied into a host-level uv configuration. The cooldown
governs dependency resolution; production normally installs the committed
`uv.lock` produced and reviewed off-server.

### Configure `.env`

Edit `/opt/promptgrimoire/.env`:

```bash
# Database — via PgBouncer Unix socket (Step 7a)
# PgBouncer handles connection pooling and prepared statement caching.
# To bypass PgBouncer (e.g., for migrations), use host=/var/run/postgresql (no port).
DATABASE__URL=postgresql+asyncpg://promptgrimoire@/promptgrimoire?host=/run/pgbouncer&port=6432
# QueuePool behind PgBouncer (see § 7a "Connection pooling behind PgBouncer")
DATABASE__USE_NULL_POOL=false
DATABASE__POOL_SIZE=20
DATABASE__MAX_OVERFLOW=10
DATABASE__POOL_PRE_PING=false
DATABASE__POOL_RECYCLE=1800

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
APP__LOG_DIR=logs/sessions
APP__DIAGNOSTIC_INTERVAL_SECONDS=300
APP__MEMORY_RESTART_THRESHOLD_MB=3072

# Claude API
LLM__API_KEY=sk-ant-...

# Standalone export worker
FEATURES__WORKER_IN_PROCESS=false
EXPORT__MAX_CONCURRENT_COMPILATIONS=1

# Load controls
ADMISSION__ENABLED=true
ADMISSION__INITIAL_CAP=10
IDLE__ENABLED=true
IDLE__TIMEOUT_SECONDS=1800
IDLE__WARNING_SECONDS=60

# Operations — generate distinct random values for both secrets
ALERTING__DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ADMIN__ADMIN_API_SECRET=
ADMIN__PRE_RESTART_TOKEN=

# Production settings
DEV__AUTH_MOCK=false
DEV__ENABLE_DEMO_PAGES=false
DEV__BRANCH_DB_SUFFIX=false
```

Production is a single NiceGUI app instance. It does not currently use Valkey
or Redis, and `NICEGUI_REDIS_URL`/`INSTANCE_ID` are not application settings on
this release. Do not install a cache service for this topology.

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
- Staff users should have `instructor` role (check via `grimoire admin show`)

#### Google OAuth Setup

**1. Create OAuth credentials** in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

- **Application type:** Web application
- **Authorized redirect URI:** Get from Stytch dashboard (OAuth → Google → Redirect URL)

**2. Enable in Stytch** dashboard → OAuth → Google:

- Enter Google Client ID and Client Secret
- JIT provisioning is controlled by the organisation's email domain settings

#### JIT Provisioning Bootstrap

Stytch email domain JIT provisioning requires at least one existing member with a verified email from each allowed domain. Before students can self-provision via Google OAuth:

1. Manually create one member with `@students.mq.edu.au` email (via magic link or `grimoire admin create`)
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
  /home/promptgrimoire/.local/bin/uv run --locked --no-sync "$@"
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
grimoire-run python scripts/setup_latex.py
```

Rebuild the LuaTeX font cache so fontspec can find system fonts (especially TeX Gyre Termes):

```bash
grimoire-run luaotfload-tool --update --force
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

### Update TinyTeX after an application release

TinyTeX maintenance is a separate release stage, not part of
`deploy/restart.sh`. Deploy and verify the application first, complete the human
UAT contract, and only then change TeX packages. This keeps an application
rollback independent from a toolchain rollback.

Run the checked maintenance script rather than pasting a strict-mode block into
an interactive shell:

```bash
sudo /opt/promptgrimoire/deploy/update-texlive.sh
```

The script pins its working directory to `/opt/promptgrimoire` before changing
to the service user. This is required because `sudo -H -u` changes `HOME` but
preserves the caller's current directory; `tlmgr` fails when that directory is
an operator home that `promptgrimoire` cannot traverse.

The script takes an exclusive maintenance lock, positively verifies an idle
export queue and active worker, stops the worker, takes an exact `.TinyTeX`
filesystem snapshot, validates its archive structure and SHA-256 checksum, records the
repository and complete installed package inventory, enables five persistent
package backups, updates `tlmgr` before all other packages, records the final
inventory, and runs `grimoire test smoke-export` before returning the worker to
service. Audit artifacts are written under
`/var/backups/promptgrimoire/texlive/`.

Jobs submitted after the worker stops remain queued and are processed when it
returns. Worker startup fails only jobs that the previous process had already
claimed as `running`; it does not discard unclaimed queued work.

If a failure occurs before package mutation, the script restarts the worker. If
a failure occurs after `tlmgr update --self` begins, it deliberately leaves the
worker stopped and prints the exact snapshot path; do not serve exports from an
unverified partial update.

After a successful script run, re-export the release's affected production
workspace. A successful command is not sufficient: open the PDF and inspect
the affected table/header boundary, annotations, CJK text, and emoji.

If the TeX update introduces a regression, keep the worker stopped and restore
the exact pre-update tree snapshot. Do not use `tlmgr restore --all` as a stage
rollback: it can select backups created by earlier maintenance and does not
guarantee the exact pre-update package set. The failed tree is retained for
forensics and the snapshot archive remains intact:

```bash
(
  set -Eeuo pipefail
  cd /opt/promptgrimoire
  tex_audit_dir=/var/backups/promptgrimoire/texlive
  tex_snapshot=$(sudo readlink -f \
    "$tex_audit_dir/latest-tree-snapshot.tar.gz")
  case "$tex_snapshot" in
    "$tex_audit_dir"/tree-before-*.tar.gz) ;;
    *) echo "ABORT: unexpected snapshot path: $tex_snapshot" >&2; exit 1 ;;
  esac
  failed_stamp=$(date +%Y%m%d-%H%M%S)
  failed_tree="/home/promptgrimoire/.TinyTeX.failed-$failed_stamp"
  sudo test -s "$tex_snapshot"
  sudo test -s "$tex_snapshot.sha256"
  sudo sha256sum -c "$tex_snapshot.sha256"
  sudo tar -tzf "$tex_snapshot" >/dev/null
  sudo test ! -e "$failed_tree"
  sudo systemctl stop promptgrimoire-worker.service
  ! sudo systemctl is-active --quiet promptgrimoire-worker.service
  sudo mv /home/promptgrimoire/.TinyTeX "$failed_tree"
  sudo tar -C /home/promptgrimoire -xzf "$tex_snapshot"
  grimoire-run grimoire test smoke-export
  sudo systemctl start promptgrimoire-worker.service
  sudo systemctl is-active --quiet promptgrimoire-worker.service
)
```

Any failed assertion exits only the subshell and leaves the worker stopped after
maintenance begins. Do not restart it until the restored tree passes the smoke
export.

> **Ref:** [TinyTeX installation](https://yihui.org/tinytex/),
> [TeX Live Manager](https://tug.org/texlive/doc/tlmgr.html)

## 10. systemd Service

Create `/etc/systemd/system/promptgrimoire.service`:

```ini
[Unit]
Description=PromptGrimoire — collaborative annotation platform
After=network-online.target postgresql.service pgbouncer.service
Wants=network-online.target
Requires=postgresql.service pgbouncer.service

[Service]
Type=simple
User=promptgrimoire
Group=promptgrimoire
WorkingDirectory=/opt/promptgrimoire
EnvironmentFile=/opt/promptgrimoire/.env
Environment=PATH=/home/promptgrimoire/.local/bin:/home/promptgrimoire/.TinyTeX/bin/x86_64-linux:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/promptgrimoire
Environment=OSFONTDIR=/usr/share/fonts:/usr/share/texmf/fonts
ExecStart=/home/promptgrimoire/.local/bin/uv run --locked --no-sync python run_prod.py
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

The main application unit is host-managed: unlike the worker unit below, it is
not stored in this repository and `deploy/restart.sh` does not reconcile it.
Treat changes to this unit or its drop-ins as a separate infrastructure stage.
Before a release after a long quiet period, compare the installed unit with
this section instead of assuming an application pull updated it. The checks run
in a subshell so an abort cannot terminate the operator's interactive shell:

```bash
(
  set -euo pipefail
  sudo systemctl cat promptgrimoire.service
  sudo systemctl show promptgrimoire.service \
    --property=FragmentPath,DropInPaths,ExecStart,MemoryHigh,MemoryMax,OOMScoreAdjust
  app_exec=$(sudo systemctl show promptgrimoire.service --property=ExecStart --value)
  if [[ "$app_exec" != *"/uv run --locked --no-sync python run_prod.py"* ]]; then
    echo 'ABORT: app unit can mutate the accepted environment at startup' >&2
    exit 1
  fi
  if ! sudo grep -Fq '/uv run --locked --no-sync "$@"' /usr/local/bin/grimoire-run; then
    echo 'ABORT: grimoire-run can mutate the accepted environment' >&2
    exit 1
  fi
)
```

Create the systemd override for resource limits and NiceGUI storage:

```bash
sudo systemctl edit promptgrimoire
```

Add between the markers:

```ini
[Service]
MemoryHigh=20G
MemoryMax=24G
OOMScoreAdjust=0
ReadWritePaths=/opt/promptgrimoire/logs /opt/promptgrimoire/.venv /home/promptgrimoire/.TinyTeX /home/promptgrimoire/.cache/uv /opt/promptgrimoire/.nicegui
```

- `MemoryHigh=20G` — applies memory pressure before the hard limit
- `MemoryMax=24G` — hard app cap; reserves 8 GB for PostgreSQL, the worker, and
  the operating system on the 32 GB host
- `OOMScoreAdjust=0` — the worker (`500`) remains the first application cgroup
  selected under system-wide memory pressure
- `ReadWritePaths` — repeats the base list plus `/opt/promptgrimoire/.nicegui` (NiceGUI session storage; without it, `ProtectSystem=strict` causes `Errno 30` on every login)

Create the `.nicegui` directory before starting:

```bash
sudo mkdir -p /opt/promptgrimoire/.nicegui
sudo chown promptgrimoire:promptgrimoire /opt/promptgrimoire/.nicegui
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

> **See also:** § 10a for the export worker service, which runs PDF exports in an isolated process with independent resource controls.

## 10a. Export Worker Service

The export worker runs PDF/LaTeX exports as a **separate systemd service**, isolated from the main application. This provides:

- **OOM isolation** — a runaway export cannot crash the app; the kernel kills the worker first
- **Independent restart** — the worker can be restarted without affecting user sessions
- **Resource controls** — best-effort CPU/IO scheduling prevents exports from starving the UI

### Installation

```bash
sudo cp deploy/promptgrimoire-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable promptgrimoire-worker
sudo systemctl start promptgrimoire-worker
```

After this one-time installation, every full deploy refreshes the installed unit from the tracked file and reloads systemd before restarting the worker. Hosts without an installed worker are left unchanged.

### Resource controls

The worker unit file applies best-effort scheduling so exports never compete with the interactive app:

| Directive | Value | Effect |
|-----------|-------|--------|
| `Nice` | `19` | Lowest CPU scheduling priority |
| `IOSchedulingClass` | `idle` | I/O only when no other process needs disk |
| `CPUWeight` | `10` | 10% CPU weight vs default 100 (systemd cgroups v2) |
| `MemoryMax` | `3G` | Hard memory cap; OOM-killed if exceeded |
| `MemoryHigh` | `2560M` | Soft limit; kernel reclaims aggressively above this |
| `OOMScoreAdjust` | `500` | Positive score = killed before lower-scored processes |

### Kernel OOM kill order

When the system is under memory pressure, the kernel kills processes in order of their OOM score. The systemd units are configured so expendable services die first:

| Service | `OOMScoreAdjust` | Kill order |
|---------|-------------------|------------|
| Export worker | `500` | 1st (expendable) |
| App (`promptgrimoire`) | `0` (default) | 2nd |
| PgBouncer | `-500` (recommended) | 3rd |
| PostgreSQL | `-1000` | Last (protect data) |

### Watchdog

The worker sends `sd_notify` heartbeats to systemd. If no heartbeat arrives within `WatchdogSec=300` (5 minutes), systemd considers the worker hung and restarts it automatically. This catches deadlocks and infinite loops without manual intervention.

The worker cancels the in-flight export job on SIGTERM and shuts down. `TimeoutStopSec=30` gives headroom for asyncio cleanup and database connection teardown. In-flight exports are marked as failed and can be retried by the user.

### Logs

```bash
# Follow worker logs
sudo journalctl -u promptgrimoire-worker -f

# Recent worker logs (last hour)
sudo journalctl -u promptgrimoire-worker --since "1 hour ago"

# Worker restarts (watchdog or crash)
sudo journalctl -u promptgrimoire-worker | grep -E "Started|Stopped|watchdog"
```

### Feature flag

In production, the main app must **not** run the export worker in-process. Set in `.env`:

```bash
FEATURES__WORKER_IN_PROCESS=false
EXPORT__MAX_CONCURRENT_COMPILATIONS=1
```

`FEATURES__WORKER_IN_PROCESS=false` tells the app not to spawn the worker in-process (the separate systemd service handles it). `EXPORT__MAX_CONCURRENT_COMPILATIONS=1` limits concurrent LaTeX compilations — the standalone worker's `MemoryMax=3G` only supports one concurrent lualatex process (each uses 200-500 MB).

## 10b. Snapshot Delivery Service (flag off by default)

The snapshot service delivers the initial annotation bundle (document HTML, highlights, tags, sidebar items) from its own process, so the NiceGUI event loop never constructs or transmits it. The app only mints a short-lived HMAC token (60 s TTL, keyed from `APP__STORAGE_SECRET`); the browser fetches the bundle directly from the service. Design and evidence: [docs/design-notes/2026-08-16-initial-snapshot-delivery.md](design-notes/2026-08-16-initial-snapshot-delivery.md).

**`SNAPSHOT__ENABLED` defaults to `false` everywhere.** With the flag off, nothing here needs to exist — no service, no HAProxy route, no config. Deploy this section only when graduating the feature. The measured win scales with document size (−19% p50 / −22% p95 page load at 100-way on large documents); small documents gain nothing, and interaction latency is unaffected either way.

### Installation

```bash
sudo cp deploy/promptgrimoire-snapshot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable promptgrimoire-snapshot
sudo systemctl start promptgrimoire-snapshot

# Verify (service binds 127.0.0.1 only)
curl -fsS http://127.0.0.1:8210/healthz
```

Unlike the export worker, the unit has **no `WatchdogSec`** — the service sends `READY`/`STOPPING` but no periodic heartbeat, so a watchdog would restart a healthy process. It also keeps **normal CPU/IO scheduling**: it serves page loads, so the worker's `Nice=19`/idle-IO settings must not be copied to it.

> **Not yet wired into `deploy/restart.sh`.** The zero-downtime deploy script manages the app and export worker only. Until restart.sh grows a snapshot stage, a full deploy requires a manual `sudo systemctl restart promptgrimoire-snapshot` after the app is healthy (the unit's `PartOf=promptgrimoire.service` covers stops via systemd, not restart.sh's flow).

### Configure `.env`

```bash
# Enable bundle delivery via the snapshot service
SNAPSHOT__ENABLED=true

# What the BROWSER fetches from. With the HAProxy path route below this is
# the app's own origin (same-origin fetch, no CORS in play):
SNAPSHOT__BASE_URL=https://grimoire.drbbs.org

# Where the service binds on 127.0.0.1
SNAPSHOT__PORT=8210

# CORS origin allowed on the bundle endpoint. Redundant when the fetch is
# same-origin via HAProxy, but set it to the app origin regardless:
SNAPSHOT__ALLOW_ORIGIN=https://grimoire.drbbs.org
```

The app and service read the same `.env`; the token is minted and verified from the shared `APP__STORAGE_SECRET`. Both processes must see the same value or every bundle fetch 403s.

### HAProxy route

The service is loopback-only; the browser reaches it through HAProxy. Add to `fe_https` (before `default_backend`) and a new backend in `/etc/haproxy/haproxy.cfg`:

```haproxy
    # In frontend fe_https:
    acl is_snapshot path /snapshot
    use_backend be_snapshot if is_snapshot

backend be_snapshot
    server snapshot 127.0.0.1:8210 check
    http-request set-header X-Forwarded-Proto https
```

Then `sudo haproxy -c -f /etc/haproxy/haproxy.cfg && sudo systemctl reload haproxy`. The app never serves a `/snapshot` route, so the path is free. `/healthz` on the service is deliberately not routed — probe it from localhost.

### Connection pooling — mandatory

The service opens its own database connections via the app's engine configuration. **It must go through PgBouncer exactly like the app** (same `DATABASE__URL`, QueuePool, `DATABASE__USE_NULL_POOL` unset). The Phase 11 load test demonstrated the failure mode: with NullPool, ~100 concurrent page loads each opened a direct PostgreSQL connection from the service and exhausted `max_connections` — surfacing to students as documents that never load, while the app itself stayed healthy. Budget the service's pool into the PgBouncer `default_pool_size` arithmetic in § 7a alongside the app and worker.

### Logs

```bash
# Follow service logs
sudo journalctl -u promptgrimoire-snapshot -f

# Bundle serves and failures (structured log)
sudo journalctl -u promptgrimoire-snapshot | grep -E "snapshot_served|snapshot_not_found"
```

Every served bundle logs `snapshot_served` with workspace/document IDs and payload size. Token failures return 403 and log nothing above INFO; a burst of browser-side load failures with a quiet service log means tokens are failing verification — check `APP__STORAGE_SECRET` parity first.

### Client behaviour when the service is down

The annotation page renders a skeleton, the bootstrap script retries the fetch once silently, then shows an unmissable red alert ("Document not loaded") with a reload button. Annotations already on the server are unaffected. Recovery is `systemctl start promptgrimoire-snapshot` + the student clicking reload; no app restart needed. Killing the service mid-session does not affect already-loaded pages — post-load collaboration flows over the app's WebSocket as before.

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
    errorfile 502 /etc/haproxy/errors/503.http
    errorfile 503 /etc/haproxy/errors/503.http
    errorfile 504 /etc/haproxy/errors/503.http

    # Forward original client info
    http-request set-header X-Forwarded-Proto https
    http-request set-header X-Real-IP %[src]
```

The `errorfile` directives serve a branded maintenance page whenever the backend is unavailable. All three error codes use the same file — 502 (connection refused), 503 (MAINT drain), 504 (gateway timeout / brownout). The source lives in `deploy/503.http`; copy it to the server and reload HAProxy:

```bash
sudo cp deploy/503.http /etc/haproxy/errors/503.http
sudo systemctl reload haproxy
```

> **Important:** HAProxy reads errorfile content at config load time. Editing the file without `systemctl reload haproxy` has no effect.

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

Fix the apparmor profile so rsyslogd can access HAProxy's chroot log socket. There are **two** required changes:

**1. Add the local rule** for the chroot socket path:

```bash
echo '/var/lib/haproxy/dev/log rw,' | sudo tee -a /etc/apparmor.d/local/usr.sbin.rsyslogd
```

**2. Add `attach_disconnected` flag** to the main profile. Without this, apparmor blocks rsyslogd from accessing paths inside HAProxy's chroot after a reload, with `"Failed name lookup - disconnected path"` errors. This is a [known Ubuntu bug](https://bugs.launchpad.net/ubuntu/+source/haproxy/+bug/2138647) affecting HAProxy + rsyslog on Ubuntu 24.04. The fix is included in rsyslog >= 8.2512.0-1ubuntu4, but on older versions you must apply it manually.

Edit `/etc/apparmor.d/usr.sbin.rsyslogd` and change the profile declaration from:

```
/usr/sbin/rsyslogd {
```

to:

```
/usr/sbin/rsyslogd flags=(attach_disconnected) {
```

Then reload and restart:

```bash
sudo apparmor_parser -r /etc/apparmor.d/usr.sbin.rsyslogd
sudo systemctl restart rsyslog
```

> **Ref:** [LP#2138647: haproxy stops logging after reload with permission denied](https://bugs.launchpad.net/ubuntu/+source/haproxy/+bug/2138647), [LP#2098148: Cannot log to bindmounted syslog socket within a chroot](https://bugs.launchpad.net/apparmor/+bug/2098148)

**Validate that HAProxy logging works** (do NOT skip this):

```bash
# 1. Check the rsyslog config exists and has the right content
cat /etc/rsyslog.d/49-haproxy.conf
# Must show: $AddUnixListenSocket, :programname filter, /var/log/haproxy.log

# 2. Check the chroot socket exists
ls -la /var/lib/haproxy/dev/log
# Must exist as a socket (type 's')

# 3. Check apparmor is not blocking rsyslog
sudo journalctl -u rsyslog --since "5 min ago" | grep -i denied
# Should show nothing.

# 4. Generate a test request and verify it appears in the log
curl -sk https://localhost/ > /dev/null 2>&1; sleep 2
sudo tail -1 /var/log/haproxy.log
# Must show a log line with the request. If the file is empty,
# rsyslog is not routing HAProxy's local0 facility.
```

> **Incident note (2026-03-16):** HAProxy logging was broken during a production incident -- `haproxy.log` was 0 bytes for the entire day. We had zero HTTP-level data for incident response. This validation section was added after that incident. Always verify after setup and after OS upgrades.

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

## 15. Monitoring

Two layers: external uptime monitoring (UptimeRobot) and internal metrics trending (Beszel). Together they cover "site is unreachable" and "server is about to die".

### External uptime — UptimeRobot

[UptimeRobot](https://uptimerobot.com/) pings the app from outside every 5 minutes. Free tier.

1. Sign up at uptimerobot.com
2. Add a monitor:
   - **Type:** HTTP(s)
   - **URL:** `https://grimoire.drbbs.org/healthz`
   - The `/healthz` endpoint accepts both GET and HEAD (added for UptimeRobot compatibility)
3. Add alert contacts:
   - **Pushbullet:** Settings → Alert Contacts → Add → Pushbullet (requires access token from pushbullet.com)
   - **Email:** Added by default on signup

### Internal metrics — Beszel

[Beszel](https://beszel.dev/) provides system metrics trending (CPU, memory, disk, network) with 30-day retention and Discord alerting. Agent on the prod box (<15 MB RAM), hub on a separate monitoring machine.

**Networking prerequisites:**

The hub listens on port 8090. The agent connects outbound to the hub. You need:

1. **NCI Cloud security group:** Create a `beszel` security group. Add an ingress rule: TCP port 8090, source CIDR `10.0.0.0/16` (internal network only — do NOT open to `0.0.0.0/0`). Attach this security group to Machine B.
2. **Machine B UFW (if enabled):** `sudo ufw allow from 10.0.0.0/16 to any port 8090 proto tcp`
3. **Machine A:** No inbound rules needed. The agent connects outbound to the hub.

**Dashboard access:** The hub dashboard is not exposed to the internet. Use an SSH tunnel:

```bash
# From your LOCAL machine
ssh -L 8090:localhost:8090 <user>@<machine-b>
# Then open http://localhost:8090 in your browser
```

**Hub setup (Machine B — monitoring server):**

```bash
# Install hub binary (no Docker required)
curl -sL https://get.beszel.dev/hub -o /tmp/install-hub.sh
chmod +x /tmp/install-hub.sh
/tmp/install-hub.sh

# Verify
sudo systemctl status beszel
```

Open the dashboard via SSH tunnel (`http://localhost:8090`). Create an admin account on first visit.

**Agent setup — Machine B (self-monitoring):**

Install the agent on the same machine as the hub:

1. In the hub dashboard, click **Add System**
2. Set the host to `localhost`
3. Copy the install command the UI generates — it includes the SSH key and token pre-filled
4. Run that command on Machine B

**Agent setup — Machine A (production server, grimoire.drbbs.org):**

1. In the hub dashboard, click **Add System**
2. Set the host to Machine A's internal IP (e.g. `10.0.0.x`)
3. Copy the install command the UI generates
4. **Before running it on Machine A**, check the `-url` flag in the command. If it says `localhost:8090`, change it to Machine B's internal IP:

```bash
# The generated command will look like:
curl -sL https://get.beszel.dev | bash -s -- -p 45876 -k "ssh-ed25519 AAAA..." -t "token..." -url "http://localhost:8090"

# Change -url to Machine B's internal IP:
curl -sL https://get.beszel.dev | bash -s -- -p 45876 -k "ssh-ed25519 AAAA..." -t "token..." -url "http://10.0.1.x:8090"
```

5. Run the corrected command on Machine A
6. If the agent was already installed with the wrong URL, fix it:

```bash
sudo systemctl edit beszel-agent
# Add between the markers:
[Service]
Environment="HUB_URL=http://<machine-b-internal-ip>:8090"

sudo systemctl daemon-reload
sudo systemctl restart beszel-agent
```

7. Verify: the hub dashboard should show Machine A as connected (green status)

**Configure alerting:**

In the hub dashboard, go to **Settings → Notifications** and add:

```
# Discord webhook
discord://{TOKEN}@{WEBHOOK_ID}
```

Then click the bell icon on the production server's card to set alert thresholds:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Memory | > 80% | OOM is imminent at 90%+ on a swapless box |
| Disk | > 85% | LaTeX temp files and logs can fill disk |
| CPU | > 90% sustained | Runaway LaTeX compilation |

**What Beszel monitors:**
- CPU, memory, disk, network (system-level)
- Per-container metrics if Docker socket is mounted
- 30-day retention (not configurable)
- Static threshold alerts only (no rate-of-change)

**What Beszel does NOT monitor:**
- PostgreSQL-specific metrics (connections, query time, locks)
- Application-level metrics (request latency, error rates)

For the current single-server setup, system-level metrics are sufficient — the 2026-03-15 OOM would have been caught by a memory > 80% alert minutes before the crash.

### PostgreSQL connection monitoring — cron

Beszel can't monitor PostgreSQL internals, so a cron job fills the gap. `deploy/check-pg-connections.sh` queries `pg_stat_activity` and posts a Discord alert when idle-in-transaction connections exceed a threshold (default: 5).

```bash
# Install the cron job (runs every 2 minutes as the promptgrimoire user)
sudo crontab -u promptgrimoire -l 2>/dev/null | {
  cat
  echo "*/2 * * * * /opt/promptgrimoire/deploy/check-pg-connections.sh"
} | sudo crontab -u promptgrimoire -

# Verify
sudo crontab -u promptgrimoire -l
```

> **Incident (2026-03-24):** 25 idle-in-transaction connections accumulated silently after a deploy, exhausting the pool before anyone noticed. This monitor would have alerted within 2 minutes.

> **Ref:** [Beszel docs](https://beszel.dev/guide/getting-started), [Beszel security model](https://beszel.dev/guide/security)

---

## 16. Verify Everything

```bash
# Services
sudo systemctl status postgresql@16-main pgbouncer
sudo systemctl status promptgrimoire
sudo systemctl status promptgrimoire-worker
sudo systemctl status haproxy
sudo systemctl status fail2ban

# App responds (`/healthz` explicitly supports GET and HEAD)
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

All `grimoire admin` commands below use the `grimoire-run` helper (installed in Step 8).

### Create a unit and add an instructor

1. **Create the unit** — log in as admin at `https://grimoire.drbbs.org/courses/new`. Fill in unit code (e.g. `LAWS1100`), name, semester (e.g. `2026-S1`). You are auto-enrolled as coordinator.

2. **Enrol your colleague** — they must have logged in at least once (AAF/magic link auto-creates their account). Then:

```bash
grimoire-run grimoire admin enroll colleague@mq.edu.au LAWS1100 2026-S1 --role instructor
```

3. **Grant Stytch instructor role** — this gives org-level privilege (copy-protection bypass, `is_privileged_user()` = true):

```bash
grimoire-run grimoire admin instructor colleague@mq.edu.au
```

Step 2 is the *course-level* role (can manage weeks, activities, settings for that unit). Step 3 is the *org-level* Stytch role (bypasses copy protection globally, sees all workspaces as owner). Both are needed for full instructor access.

### User management

```bash
# List all users who have logged in
grimoire-run grimoire admin list

# List all users including pre-created
grimoire-run grimoire admin list --all

# Show a user's details and enrollments
grimoire-run grimoire admin show colleague@mq.edu.au

# Pre-create a user (before they've logged in)
grimoire-run grimoire admin create colleague@mq.edu.au --name "Jane Smith"

# Grant/revoke org-level admin
grimoire-run grimoire admin admin colleague@mq.edu.au
grimoire-run grimoire admin admin colleague@mq.edu.au --remove

# Grant/revoke Stytch instructor role
grimoire-run grimoire admin instructor colleague@mq.edu.au
grimoire-run grimoire admin instructor colleague@mq.edu.au --remove

# Change a user's course role
grimoire-run grimoire admin role colleague@mq.edu.au LAWS1100 2026-S1 coordinator

# Remove a user from a course
grimoire-run grimoire admin unenroll colleague@mq.edu.au LAWS1100 2026-S1
```

**Available course roles** (in ascending privilege): `student`, `tutor`, `instructor`, `coordinator`. Roles marked `is_staff` (`instructor`, `coordinator`) can see unpublished weeks, manage activities, and edit locked tags.

### Role model

Three independent layers determine what a user can do:

| Layer | Scope | Grants | Set via |
|-------|-------|--------|---------|
| **Org admin** | Global | Owner of all workspaces, bypasses all ACLs | `grimoire admin admin` |
| **Stytch instructor** | Global | `is_privileged_user()` = true, bypasses copy protection | `grimoire admin instructor` (or AAF `eduperson_affiliation=staff`) |
| **Course role** | Per-unit | `student`/`tutor`/`instructor`/`coordinator` — controls week visibility, activity settings, tag locks | `grimoire admin enroll --role` or `grimoire admin role` |

A user typically needs both a **course role** (to see the unit's content) and the **Stytch instructor role** (for global privileges). Org admin is reserved for you.

### Course and activity settings (UI)

All course/activity configuration is done through the web UI:

- **Unit settings** — click the settings icon on the course page. Controls defaults for copy protection, sharing, anonymous sharing, and tag creation.
- **Week management** — create weeks, publish/unpublish (students only see published weeks).
- **Activity settings** — per-activity overrides using tri-state (on/off/inherit from unit). Controls copy protection, sharing, tag creation, and anonymity.
- **Tag management** — open from any workspace's annotation page. Create/edit tag groups and tags, import from CSV/JSON, lock tags (students can't modify locked tags), drag-reorder.

### Deploy an update

Production uses Bash. For a guarded release, copy stages 2–4 into an
operator-owned script outside the checkout, set `accepted_commit` at the top,
check it with `bash -n`, and run the script. Do not paste `set -euo pipefail` or
an `exit`-guarded release block into an interactive shell: a failed guard will
terminate that shell. Keep stages 2–4 in the same script so their captured
timestamps and commit identifiers remain available to later verification.

#### 1. Accept the candidate off-server

Before touching production:

- record the full, CI-approved candidate SHA as `accepted_commit`; do not derive
  it later from a moving branch name;
- require clean GitHub CI for the candidate;
- for a release after a long quiet period, run `uv run grimoire e2e slow` (or
  the equivalent nightly workflow) against the exact candidate; this command
  is a strict gate: isolation retry-passes fail the run and the serial
  compiled-PDF lane does not retry. Like every `grimoire test` and `grimoire
  e2e` command on Linux, it queues behind any test run from another worktree,
  waits for host load to settle, reserves one available CPU, and lowers its
  process tree to nice level 19 (plus idle I/O scheduling when `ionice` is
  installed), so no external `taskset`/`nice` wrapper is required;
- review the commit range for Alembic migrations and write a compatible
  rollback plan for every schema change; and
- keep application, TeX, and wider infrastructure changes in separate stages.

The production deploy gate complements CI; it does not replace the browser,
NiceGUI, integration, BATS, or JS lanes already run off-server.

#### 2. Capture production state and back up

```bash
cd /opt/promptgrimoire
set -euo pipefail
: "${accepted_commit:?set accepted_commit to the full CI-approved SHA}"
if [[ ! "$accepted_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'ABORT: accepted_commit must be a full 40-character lowercase SHA' >&2
  exit 1
fi
deploy_started_at=$(date -Is)

sudo -H -u promptgrimoire git -C /opt/promptgrimoire status --short --branch
if [[ -n "$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire status --porcelain)" ]]; then
  echo "ABORT: production worktree is not clean" >&2
  exit 1
fi

sudo -H -u promptgrimoire git -C /opt/promptgrimoire fetch origin main
checkout_commit=$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire rev-parse HEAD)
remote_main=$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire rev-parse origin/main)
if [[ "$remote_main" != "$accepted_commit" ]]; then
  echo "ABORT: origin/main moved from accepted $accepted_commit to $remote_main" >&2
  exit 1
fi
candidate_commit=$accepted_commit

# restart.sh refreshes the tracked worker unit, but not this host-managed app
# unit. Record it now; reconcile any drift as a separate infrastructure stage.
sudo systemctl cat promptgrimoire.service
sudo systemctl show promptgrimoire.service \
  --property=FragmentPath,DropInPaths,ExecStart,MemoryHigh,MemoryMax,OOMScoreAdjust
app_exec=$(sudo systemctl show promptgrimoire.service --property=ExecStart --value)
if [[ "$app_exec" != *"/uv run --locked --no-sync python run_prod.py"* ]]; then
  echo 'ABORT: app unit can mutate the accepted environment at startup' >&2
  exit 1
fi
if ! sudo grep -Fq '/uv run --locked --no-sync "$@"' /usr/local/bin/grimoire-run; then
  echo 'ABORT: grimoire-run can mutate the accepted environment' >&2
  exit 1
fi

worker_in_process=$(sudo awk -F= \
  '$1=="FEATURES__WORKER_IN_PROCESS" {value=$2} END {print value}' \
  /opt/promptgrimoire/.env)
worker_concurrency=$(sudo awk -F= \
  '$1=="EXPORT__MAX_CONCURRENT_COMPILATIONS" {value=$2} END {print value}' \
  /opt/promptgrimoire/.env)
if [[ "$worker_in_process" != "false" || "$worker_concurrency" != "1" ]]; then
  echo "ABORT: production export-worker topology does not match the runbook" >&2
  exit 1
fi
if ! sudo systemctl is-enabled --quiet promptgrimoire-worker.service; then
  echo 'ABORT: standalone export worker is not enabled' >&2
  exit 1
fi
if ! sudo systemctl is-active --quiet promptgrimoire-worker.service; then
  echo 'ABORT: standalone export worker is not active' >&2
  exit 1
fi
printf 'worker_topology=standalone-one-at-a-time\n'

# HEAD may already contain a candidate from an earlier pre-restart abort. Read
# the commit bound to a process in the running app's systemd cgroup instead.
# MainPID is uv; the structured logger runs in its Python child.
structured_log=/opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl
app_cgroup=$(sudo systemctl show promptgrimoire.service --property=ControlGroup --value)
if [[ -z "$app_cgroup" || ! -r "/sys/fs/cgroup${app_cgroup}/cgroup.procs" ]]; then
  echo "ABORT: promptgrimoire has no readable systemd cgroup" >&2
  exit 1
fi
app_pids=$(sudo jq -Rsc 'split("\n") | map(select(length > 0) | tonumber)' \
  "/sys/fs/cgroup${app_cgroup}/cgroup.procs")
running_short=$(sudo tail -n 5000 "$structured_log" \
  | jq -r --argjson app_pids "$app_pids" \
    'select((.pid as $pid | $app_pids | index($pid)) != null
      and .commit != null and .commit != "unknown") | .commit' \
  | tail -n 1)
if [[ ! "$running_short" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "ABORT: could not identify the running application commit" >&2
  exit 1
fi
rollback_commit=$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire \
  rev-parse "${running_short}^{commit}")

printf 'deploy_started_at=%s\nrunning_commit=%s\ncheckout_commit=%s\ncandidate_commit=%s\n' \
  "$deploy_started_at" "$rollback_commit" "$checkout_commit" "$candidate_commit"
if [[ "$checkout_commit" != "$rollback_commit" ]]; then
  echo "NOTICE: checkout differs from the running process (prior aborted deploy?)"
fi

migration_count=$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire \
  diff --name-only "$rollback_commit..$candidate_commit" -- alembic/versions/ \
  | wc -l)
printf 'migration_files=%s\n' "$migration_count"
sudo -H -u promptgrimoire git -C /opt/promptgrimoire \
  diff --name-status "$rollback_commit..$candidate_commit" -- alembic/versions/

sudo /usr/local/bin/promptgrimoire-backup
```

Treat a non-zero `migration_files` count as a stop, not an informational
message, until the forward and rollback migration procedures have been reviewed.
The backup is only accepted when the command names the uploaded archive and
reports a successful transfer.

#### 3. Deploy the application

Fast-forward to the captured commit object—not the moving `origin/main` name—
before invoking the script. The script requires the same full SHA and never
fetches or pulls. This guarantees that the tree tested and restarted is the
candidate accepted off-server, even if `main` advances during the deployment.

```bash
sudo -H -u promptgrimoire git -C /opt/promptgrimoire \
  merge --ff-only "$candidate_commit"
deployed_checkout=$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire rev-parse HEAD)
if [[ "$deployed_checkout" != "$candidate_commit" ]]; then
  echo "ABORT: checkout does not match the captured candidate" >&2
  exit 1
fi
sudo /opt/promptgrimoire/deploy/restart.sh \
  --expected-commit "$candidate_commit"
deploy_finished_at=$(date -Is)
printf 'deploy_finished_at=%s\n' "$deploy_finished_at"
```

The deploy script takes an exclusive deployment lock, verifies the pinned clean
checkout and mandatory standalone-worker topology, and builds a commit-keyed
Python environment with `uv sync --locked` without mutating the live `.venv`.
It then runs `npm ci --include=dev` and the e-stop tests against that staged
environment, revalidates the exact tested tree, refreshes the installed worker
unit, updates the HAProxy 503 page, and performs the pre-restart flush (CRDT persist + session
invalidation + parallel client disconnect) → HAProxy drain → wait for
connections to drain → stop the export worker → HAProxy maintenance → stop the
app → prune stale NiceGUI storage → select the accepted environment through the
`.venv` symlink → start the app → wait for `/healthz` → start the worker →
HAProxy ready. Service starts use `uv run --locked --no-sync`, so they cannot
silently add or remove packages after the staged exact sync passes.

The test e-stop has explicit environment semantics:

- Python unit tests, BATS, JavaScript tests, and the PDF export smoke test are
  mandatory. A missing runner, test directory, or test dependency fails the
  gate; it is never an automatic pass.
- The host must provide `bats`, Node.js, and npm. `restart.sh` installs the
  reviewed JavaScript dependency graph from `package-lock.json` with
  `npm ci --include=dev` before running the gate.
- JavaScript tests use only `node_modules/.bin/vitest`. A global `npx` is not a
  test dependency and must never select or download an unreviewed runner.
  `npm ci` owns lockfile validation and clean dependency installation; the lane
  then requires and executes the repository-local runner it installed.
- Node.js remains deployment/test tooling rather than an application runtime
  dependency. Upgrade it as a separate infrastructure stage, not inside an
  application deployment.

The repository's `.npmrc` requires npm 11.10 or newer to enforce
`min-release-age=14`. An older npm can still reproduce the reviewed lock with
`npm ci`, but it does not enforce that age policy; record and resolve that host
provisioning gap separately rather than changing npm during the app restart.

If the script aborts during candidate verification, staged locked sync, or the
test e-stop, HAProxy and systemd have not been touched: the old process and its
selected `.venv` are still serving traffic. The operator has already
fast-forwarded the checkout, so candidate static files may be visible; the
Python environment is not selected until after the app stops. Investigate the
named gate. Do not turn `--skip-tests` into the normal recovery path. A future
release-directory deployment should also make the source-tree switch atomic;
the current mutable-checkout topology cannot provide that property.

`--skip-tests` exists for an operator-declared emergency only, after the exact
candidate has passed the full off-server gates and the reason for bypassing the
production e-stop has been recorded:

```bash
sudo /opt/promptgrimoire/deploy/restart.sh \
  --expected-commit "$candidate_commit" --skip-tests
```

Alembic migrations run automatically on app start.

#### 4. Verify the deployed application positively

Do not infer success from a quiet terminal or an empty error query. Require
positive service, unit-file, health, and database signals:

```bash
running_checkout=$(sudo -H -u promptgrimoire git -C /opt/promptgrimoire rev-parse HEAD)
if [[ "$running_checkout" != "$candidate_commit" ]]; then
  echo "ABORT: post-deploy checkout is not the accepted candidate" >&2
  exit 1
fi
printf 'running_checkout=%s\n' "$running_checkout"

for service in promptgrimoire promptgrimoire-worker haproxy pgbouncer postgresql@16-main; do
  if ! sudo systemctl is-active --quiet "$service"; then
    echo "ABORT: $service is not active" >&2
    exit 1
  fi
  printf 'service_active=%s\n' "$service"
done

if sudo cmp -s \
  /opt/promptgrimoire/deploy/promptgrimoire-worker.service \
  /etc/systemd/system/promptgrimoire-worker.service; then
  echo 'worker_unit=tracked'
else
  echo 'worker_unit=mismatch' >&2
  exit 1
fi

if curl --fail --show-error --silent http://127.0.0.1:8080/healthz; then
  printf '\nlocal_healthz=ok\n'
else
  echo 'ABORT: local health check failed' >&2
  exit 1
fi
if curl --fail --show-error --silent https://grimoire.drbbs.org/healthz; then
  printf '\npublic_healthz=ok\n'
else
  echo 'ABORT: public health check failed' >&2
  exit 1
fi

sudo systemctl show promptgrimoire \
  --property=MainPID,ExecMainStartTimestamp,ActiveState,SubState
sudo systemctl show promptgrimoire-worker \
  --property=MainPID,ExecMainStartTimestamp,ActiveState,SubState

sudo -u promptgrimoire psql -v ON_ERROR_STOP=1 -d promptgrimoire \
  -c 'SELECT 1 AS database_ok;'
sudo -u promptgrimoire psql -v ON_ERROR_STOP=1 -c \
  "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'promptgrimoire' GROUP BY state ORDER BY state;"
```

Then inspect the bounded deploy window. An empty result is not itself a pass;
the positive checks above establish that the query reached live components.

```bash
sudo journalctl -u promptgrimoire -u promptgrimoire-worker \
  --since "$deploy_started_at" --until "$deploy_finished_at" --no-pager
```

Expected database states are `active` and `idle`. If `idle in transaction`
appears and climbs, restart and investigate before admitting the release.

#### 5. Human UAT gate

Stop here and hand control to the release operator. Automated browser lanes use
mock authentication, so a production release that changes authentication or its
dependencies requires a real Stytch exercise.

In the release transcript, record
`uat_started_at=$(date -u +'%Y-%m-%dT%H:%M:%S.%6NZ')`, the UAT account,
workspace UUID, export job UUID, and
`uat_finished_at=$(date -u +'%Y-%m-%dT%H:%M:%S.%6NZ')`. Use a named non-student
UAT workspace and remove the temporary highlight/annotation after the
persistence check so the test does not become unexplained production data.

Record pass/fail for each falsifiable claim:

1. In a private browser session, request and consume a real Stytch magic link;
   the user lands in PromptGrimoire authenticated as the expected account.
2. Open a non-student production UAT workspace, create a highlight and
   annotation, reload the page, and observe both persisted once (no duplicate).
3. Export the release's affected production workspace as PDF. Open it and
   inspect the affected table/header boundary, body text, annotations, CJK, and
   emoji—not merely the HTTP response or file size.
4. Navigate away and back through the normal Unit/activity/workspace path; the
   annotation workflow remains usable and no new ERROR/CRITICAL alert is emitted
   for the UAT actions.

Inspect the exact UAT interval rather than an unbounded tail:

```bash
sudo journalctl -u promptgrimoire -u promptgrimoire-worker \
  --since "$uat_started_at" --until "$uat_finished_at" --no-pager
sudo jq --arg start "$uat_started_at" --arg finish "$uat_finished_at" \
  'select(.timestamp >= $start and .timestamp <= $finish and
          (.level == "error" or .level == "critical"))' \
  /opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl
```

The positive browser actions establish that the UAT reached the live system;
the bounded error query is supporting evidence, not a pass merely because it
returned no rows.

Do not update TinyTeX until the operator explicitly accepts this gate. If UAT
fails, leave TeX unchanged and roll back or repair the application layer first.

#### 6. TinyTeX and first-day observation

After UAT acceptance, follow [Update TinyTeX after an application
release](#update-tinytex-after-an-application-release), then repeat the export
smoke test and affected-workspace PDF inspection.

For the first day after a long-stale release, watch Beszel memory and CPU,
event-loop lag diagnostics, PgBouncer waiting clients, worker restarts, and
Discord ERROR/CRITICAL alerts. Compare against the pre-deploy baseline rather
than treating the absence of an alert as evidence of normal operation.

#### Rollback

The `rollback_commit` captured from the live process's structured log identifies
the previous running application tree. It can differ from the checkout after an
earlier deploy changed files or dependencies but aborted before restart.
The normal rollback is to revert the release on `main`, let CI gate the revert,
capture that revert commit as a new candidate, then run this deployment
procedure again with its full SHA. Do not locally detach or reset production:
that creates an unreviewed deployment outside the pinned-candidate procedure.

If the release included schema changes, follow its reviewed migration rollback
plan. If data must be restored, use [Restore procedure](#restore-procedure); that
is destructive and requires an explicit decision about data created since the
backup.

> **Incident (2026-03-24):** A deploy introduced a session leak that accumulated
> 25 idle-in-transaction connections, exhausting the pool (69/80 checked out)
> and causing 60s timeouts on all page loads. The app had to be restarted. See
> postmortem (forthcoming).

**One-time setup** (after first deploy of the script):

```bash
sudo mkdir -p /etc/haproxy/errors
sudo cp /opt/promptgrimoire/deploy/503.http /etc/haproxy/errors/503.http
# Add errorfile line to backend (see § 11. HAProxy above), then:
sudo haproxy -c -f /etc/haproxy/haproxy.cfg && sudo systemctl reload haproxy
```

**Recovery** — if a deploy fails mid-restart and HAProxy is stuck in maintenance mode:

```bash
echo "set server be_promptgrimoire/app state ready" | sudo socat stdio /run/haproxy/admin.sock
```

### View logs

```bash
# App (systemd journal) — real-time tail
sudo journalctl -u promptgrimoire -f

# Errors only (real-time) — works regardless of logging framework
sudo journalctl -u promptgrimoire -f -p err

# Errors in a time window
sudo journalctl -u promptgrimoire --no-pager -S "11:00" -U "11:15" | grep -A5 "error"

# Structured JSON log file (see docs/logging.md for jq queries)
sudo tail -f /opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl | jq .

# Errors and criticals from structured log
sudo tail -f /opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl | jq 'select(.level == "error" or .level == "critical")'

# HAProxy
sudo tail -f /var/log/haproxy.log

# fail2ban
sudo tail -f /var/log/fail2ban.log

# Backup
sudo tail -f /var/log/promptgrimoire-backup.log
```

**Known gap:** Errors from third-party libraries (aiohttp, uvicorn) that log via stdlib `logging` bypass the structlog Discord alert processor. Use `journalctl -p err` to catch everything. See #359.

### Health checks

```bash
# All services running?
sudo systemctl status postgresql@16-main pgbouncer promptgrimoire \
  promptgrimoire-worker haproxy fail2ban

# App responds? (/healthz supports HEAD + GET for UptimeRobot)
curl -s -o /dev/null -w "%{http_code}" https://grimoire.drbbs.org/healthz

# TLS certificate valid?
echo | openssl s_client -connect grimoire.drbbs.org:443 -servername grimoire.drbbs.org 2>/dev/null \
  | openssl x509 -noout -dates

# Database?
sudo -u promptgrimoire psql -d promptgrimoire -c "SELECT 1;"

# PgBouncer pool health? (cl_waiting > 0 sustained = pool saturated)
sudo -u promptgrimoire psql -h /run/pgbouncer -p 6432 -d pgbouncer -c "SHOW POOLS;"

# Connection pool health? (idle in transaction = leak)
sudo -u promptgrimoire psql -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'promptgrimoire' GROUP BY state ORDER BY count DESC;"

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
grimoire-run grimoire seed run
```

Idempotent — safe to run multiple times.

### Planned maintenance (take site offline)

HAProxy reads `errorfile` content at config load time. Editing the file on disk
does **not** take effect until HAProxy reloads.

1. Edit the 503 page with your custom message:
   ```bash
   sudo vim /etc/haproxy/errors/503.http
   ```
2. Reload HAProxy so it picks up the new file:
   ```bash
   sudo systemctl reload haproxy
   ```
3. Stop the app (HAProxy must have no backend before it serves 503 — if the
   app is still running, HAProxy routes to it instead of serving the error page):
   ```bash
   sudo systemctl stop promptgrimoire
   ```
4. Put HAProxy in maintenance mode:
   ```bash
   echo 'set server be_promptgrimoire/app state maint' | sudo socat stdio /run/haproxy/admin.sock
   ```

Users now see your custom 503 page.

**Bring it back up:**

```bash
sudo systemctl start promptgrimoire
# Wait for /healthz
until curl -sf http://127.0.0.1:8080/healthz > /dev/null 2>&1; do sleep 1; done
echo 'set server be_promptgrimoire/app state ready' | sudo socat stdio /run/haproxy/admin.sock
```

**Important:** Always restore the standard 503 page after planned maintenance,
otherwise the next deploy will overwrite it with the repo version anyway:
```bash
sudo cp /opt/promptgrimoire/deploy/503.http /etc/haproxy/errors/503.http
sudo systemctl reload haproxy
```

### Session invalidation on restart

Sessions are invalidated in three ways, covering all restart paths:

| Restart path | Mechanism | How it works |
|---|---|---|
| `deploy/restart.sh` | `POST /api/pre-restart` | Flushes CRDT, sync-writes storage files with `auth_user` removed |
| Memory threshold auto-restart | `graceful_memory_shutdown()` | Same sync-write, then navigates clients to `/restarting` |
| Bare `systemctl restart` / OOM / crash | `invalidate_sessions_on_disk()` at startup | Iterates `.nicegui/storage-user-*.json` on disk, removes `auth_user` before accepting connections |

After any restart, users must log in again. The HAProxy 503 page (manual deploys)
and the NiceGUI `/restarting` page (auto-restart) both inform users of this.

### Memory threshold auto-restart

The app monitors RSS every `APP__DIAGNOSTIC_INTERVAL_SECONDS` (default: 300s).
When RSS exceeds `APP__MEMORY_RESTART_THRESHOLD_MB` (default: 3072):

1. Logs `memory_threshold_exceeded_restarting` at CRITICAL (triggers Discord alert)
2. Flushes Milkdown editors to CRDT
3. Persists dirty CRDT state to database
4. Navigates connected clients to `/restarting?manual=1` (shows "Log in" button when ready)
5. Sync-writes session invalidation to disk
6. Exits with code 75 (systemd `Restart=on-failure` triggers automatic restart)

**Tuning** (in `/opt/promptgrimoire/.env`):
```bash
APP__DIAGNOSTIC_INTERVAL_SECONDS=300     # Check interval (lower = faster response)
APP__MEMORY_RESTART_THRESHOLD_MB=3072    # RSS threshold (lower = more headroom before saturation)
# Set to 0 to disable auto-restart:
# APP__MEMORY_RESTART_THRESHOLD_MB=0
```

Changes require a restart to take effect.

### NiceGUI storage file cleanup

NiceGUI stores per-user session data in `.nicegui/storage-user-*.json` files
that are **never automatically cleaned up**. `deploy/restart.sh` prunes files
older than 7 days on each deploy. For manual cleanup:

```bash
# As promptgrimoire user:
find /opt/promptgrimoire/.nicegui -name "storage-user-*.json" -mtime +7 -delete
```

### HAProxy recovery

If a deploy fails mid-restart and HAProxy is stuck in drain or maintenance mode:

```bash
# Check current state
echo 'show servers state' | sudo socat stdio /run/haproxy/admin.sock

# Restore normal traffic
echo 'set server be_promptgrimoire/app state ready' | sudo socat stdio /run/haproxy/admin.sock
```

**Note:** `socat` to the admin socket requires root. Use `sudo`.

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
| HAProxy 503 page | `/etc/haproxy/errors/503.http` (source: `deploy/503.http`) — reload HAProxy after editing |
| NiceGUI storage | `/opt/promptgrimoire/.nicegui/storage-user-*.json` (pruned on deploy) |
| Deploy script | `/opt/promptgrimoire/deploy/restart.sh` |
| HAProxy combined cert | `/etc/haproxy/certs/grimoire.drbbs.org.pem` |
| Let's Encrypt certs | `/etc/letsencrypt/live/grimoire.drbbs.org/` |
| Cert smush script | `/usr/local/bin/haproxy-cert-smush` |
| Certbot deploy hook | `/etc/letsencrypt/renewal-hooks/deploy/50-haproxy.sh` |
| Certbot renewal config | `/etc/letsencrypt/renewal/grimoire.drbbs.org.conf` |
| fail2ban config | `/etc/fail2ban/jail.local` |
| PgBouncer config | `/etc/pgbouncer/pgbouncer.ini` |
| PgBouncer log | `/var/log/pgbouncer/pgbouncer.log` |
| PostgreSQL data | `/var/lib/postgresql/` (default) |
| TinyTeX | `/home/promptgrimoire/.TinyTeX/` |
| Backup script | `/usr/local/bin/promptgrimoire-backup` |
| Backup log | `/var/log/promptgrimoire-backup.log` |
| Local backup staging | `/var/backups/promptgrimoire/` |
| SharePoint backup | `sharepoint:PromptGrimoire/backups/` |

## Known Limitations

- **Hot reload** is on by default (`PROMPTGRIMOIRE_RELOAD=1`). `run_prod.py` disables it. `run.py` (dev) keeps it.
- **Single process.** NiceGUI + uvicorn handles connections asynchronously. No horizontal scaling. Practical ceiling ~300-400 concurrent users before GC pauses and memory pressure become untenable. See `docs/nicegui/production-memory-management.md`. PgBouncer handles connection pooling for up to 500 concurrent clients.
- **One export at a time.** LaTeX compilation is isolated in the standalone
  worker and `EXPORT__MAX_CONCURRENT_COMPILATIONS=1` protects its 3 GB cgroup;
  export requests queue during bursts.
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
| PostgreSQL tuning | https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server |
| PostgreSQL resource config | https://www.postgresql.org/docs/16/runtime-config-resource.html |
| PostgreSQL WAL config | https://www.postgresql.org/docs/16/wal-configuration.html |
| pgtune | https://pgtune.leopard.in.ua/ |
| PgBouncer configuration | https://www.pgbouncer.org/config.html |
| PgBouncer usage (SHOW) | https://www.pgbouncer.org/usage.html |
| PgBouncer 1.21 prepared statements | https://www.postgresql.org/about/news/pgbouncer-1210-released-now-with-prepared-statements-2735/ |
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
