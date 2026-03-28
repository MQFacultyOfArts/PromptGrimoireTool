# Infrastructure Migration & Worker Isolation Design

**GitHub Issue:** None

## Summary

The application currently runs as a single process on an NCI Cloud VM: the NiceGUI web server, the PDF export worker, and PostgreSQL all share the same systemd cgroup and memory address space. When LaTeX compilation spikes memory (up to 1.25 GB per job, two jobs in parallel), the kernel OOM killer can terminate the entire application rather than just the offending export. This design documents a migration to a DigitalOcean droplet in Sydney that resolves this through process isolation — three independent systemd services, each with their own resource controls, restart policies, and OOM priority.

The approach has two separable concerns. First, the export worker is extracted from the NiceGUI process into a standalone service with its own database engine, systemd watchdog heartbeating, and cgroup memory ceiling. The app retains an in-process worker mode (via a feature flag) so local development continues to need only `uv run run.py`. Second, the database connection layer is corrected: the app currently runs SQLAlchemy's own connection pool in front of PgBouncer, creating two competing layers of pooling. Replacing SQLAlchemy's pool with `NullPool` makes PgBouncer the single source of truth for connection management. The migration itself — from NCI to DigitalOcean — reduces hosting costs by 88–94% while meeting the Australian data residency requirement, and NCI is repurposed as a streaming replication standby rather than decommissioned.

## Definition of Done

1. **Production runs on a single DO Sydney droplet** (16 vCPU / 32 GB) with three isolated systemd units: app, export worker, PostgreSQL — each independently resource-controlled and restartable.
2. **Export worker runs as a separate systemd service** with best-effort scheduling (`Nice=19`, `IOSchedulingClass=idle`, `MemoryMax=3G`, `OOMScoreAdjust=500`) and watchdog monitoring (`WatchdogSec`, `sd_notify`).
3. **PostgreSQL is kernel-protected** (`OOMScoreAdjust=-1000`) — never killed before the worker or app.
4. **Connection pooling uses NullPool** behind PgBouncer (togglable via `DATABASE__USE_NULL_POOL`), eliminating double-pool pathology. Existing pool config retained for non-PgBouncer environments.
5. **Worker health is monitored** — systemd watchdog auto-restarts on heartbeat failure; Discord webhook alerts on queue depth >10.
6. **PostgreSQL has streaming replication** to NCI standby for operational resilience (in addition to nightly pg_dump → SharePoint).
7. **Zero data loss during migration** — verified by pre/post record counts and CRDT integrity check.
8. **Downtime under 1 hour** — HAProxy maintenance page, pg_dump/restore, DNS cutover.
9. **Deployment guide updated** — `docs/deployment.md` reflects new topology, worker service, and resource controls.
10. **Worker runs in-process in dev** — feature-flagged via `FEATURES__WORKER_IN_PROCESS` so `uv run run.py` starts everything locally.

**Out of scope:**
- Multi-machine split — process isolation sufficient for current load; revisit if resource contention emerges
- Containerisation — staying with systemd + uv
- Horizontal scaling — single NiceGUI process
- Search worker / deadline worker extraction — lightweight, remain in-process
- App-level fixes (#419 thundering herd, #369 event loop pressure) — proceed independently

## Acceptance Criteria

### infra-split.AC1: Worker runs as standalone process
- **infra-split.AC1.1 Success:** `python -m promptgrimoire.export.worker_main` starts, initialises DB engine, and begins polling
- **infra-split.AC1.2 Success:** Standalone worker claims a queued job and produces a PDF
- **infra-split.AC1.3 Failure:** Standalone worker handles DB unavailability gracefully (logs error, retries on next poll)
- **infra-split.AC1.4 Success:** SIGTERM causes the worker to finish the current job and exit cleanly

### infra-split.AC2: NullPool toggle works
- **infra-split.AC2.1 Success:** `DATABASE__USE_NULL_POOL=true` causes `create_async_engine` to use `NullPool`
- **infra-split.AC2.2 Success:** `DATABASE__USE_NULL_POOL=false` (default) uses `QueuePool` with configured pool_size/max_overflow
- **infra-split.AC2.3 Edge:** Pool status logging (`_pool_status()`) does not error when pool is `NullPool`

### infra-split.AC3: Worker watchdog integration
- **infra-split.AC3.1 Success:** Worker sends `READY=1` after DB init and `WATCHDOG=1` on each poll cycle
- **infra-split.AC3.2 Failure:** Watchdog heartbeat continues during a long-running LaTeX compilation (event loop not blocked)

### infra-split.AC4: Queue depth monitoring
- **infra-split.AC4.1 Success:** Queue depth >10 triggers Discord webhook with count and oldest timestamp
- **infra-split.AC4.2 Success:** Queue depth ≤10 does not trigger an alert

### infra-split.AC5: Deployment guide accuracy
- **infra-split.AC5.1 Success:** `docs/deployment.md` includes worker service setup, resource controls, NullPool config
- **infra-split.AC5.2 Success:** `deploy/restart.sh` restarts both app and worker services

### infra-split.AC6: Streaming replication
- **infra-split.AC6.1 Success:** `pg_stat_replication` on primary shows standby in `streaming` state
- **infra-split.AC6.2 Failure:** Replication lag exceeding threshold triggers Discord alert

### infra-split.AC7: In-process dev mode
- **infra-split.AC7.1 Success:** `FEATURES__WORKER_IN_PROCESS=true` (default) causes app to spawn export worker as asyncio task
- **infra-split.AC7.2 Success:** `FEATURES__WORKER_IN_PROCESS=false` causes app to skip worker spawn

### infra-split.AC8: Minimal data loss migration
- **infra-split.AC8.1 Success:** Pre/post migration row counts match for all tables
- **infra-split.AC8.2 Edge:** ~~CRDT state spot-check~~ **Waived.** `pg_dump -Fc` custom format includes per-block checksums; CRDT corruption from a clean dump/restore is not a realistic failure mode. If the app was stopped cleanly, CRDT loss is zero. If the app crashed before dump, in-flight edits from the last seconds may be lost — acceptable for an offline tool.
- **infra-split.AC8.3 Success:** Post-migration smoke test passes (login, open workspace, mass export check)

## Glossary

- **cgroup (control group):** A Linux kernel feature that limits and isolates resource usage (CPU, memory, I/O) for a group of processes. systemd maps each service to its own cgroup, so resource limits set on a service only affect that service.
- **OOM killer:** The Linux kernel mechanism that terminates processes when the system runs out of memory. It selects victims using `OOMScoreAdjust` — higher scores are killed first, -1000 disables killing entirely.
- **OOMScoreAdjust:** A per-process integer (-1000 to 1000) that biases the kernel OOM killer toward or away from a process. The export worker is set to 500 (killed first), PostgreSQL to -1000 (never killed).
- **MemoryMax:** A hard memory ceiling enforced by the cgroup. When a process exceeds it the OOM killer is invoked against that cgroup immediately. Distinct from `MemoryHigh`, which throttles rather than kills.
- **Nice / `Nice=19`:** A Unix process scheduling priority. Higher nice value = lower CPU priority. Nice 19 means the worker only gets CPU when no other process wants it.
- **IOSchedulingClass=idle:** A Linux I/O scheduler class meaning the process only receives disk I/O when no other process has pending I/O.
- **CPUWeight:** A systemd cgroup v2 setting controlling relative CPU share under contention. Default is 100; the worker is set to 10.
- **systemd watchdog / `sd_notify`:** A systemd protocol where a service sends keepalive pings (`WATCHDOG=1`) via a Unix socket. If pings stop arriving within `WatchdogSec`, systemd kills and restarts the service.
- **PgBouncer:** A connection pooler that sits in front of PostgreSQL. In transaction mode, a server connection is only held for the duration of one database transaction.
- **Transaction mode (PgBouncer):** A pooling mode where a server connection is assigned per transaction rather than per client session. Incompatible with SET, LISTEN, advisory locks, WITH HOLD cursors.
- **NullPool:** A SQLAlchemy pool implementation that opens a new database connection for every request and closes it immediately after. The correct configuration when PgBouncer handles pooling.
- **QueuePool:** SQLAlchemy's default connection pool, which maintains a fixed set of open connections. Running QueuePool behind PgBouncer creates double-pooling.
- **Double-pooling:** The pathology of running two independent connection pools in series. Can cause prepared statement errors, redundant queuing, and pool exhaustion in one layer while the other has idle capacity.
- **`pool_pre_ping`:** A SQLAlchemy option that tests a connection before using it. Interacts badly with PgBouncer transaction mode.
- **WAL (Write-Ahead Log):** PostgreSQL's durability log. Streaming replication works by shipping WAL records from primary to standby in near real-time.
- **Streaming replication:** A PostgreSQL high-availability mechanism where a standby continuously receives and replays WAL records from the primary.
- **`pg_stat_replication`:** A PostgreSQL system view on the primary showing replication state and lag per connected standby.
- **`pg_basebackup`:** The PostgreSQL utility for taking an initial full copy of a primary to bootstrap a standby.
- **`FOR UPDATE SKIP LOCKED`:** A PostgreSQL locking clause used in job queue queries. Each worker sees only unclaimed rows and skips rows another worker has locked.
- **DNS TTL:** Time-to-live on a DNS record, controlling how long resolvers cache the IP address.
- **SYD1:** DigitalOcean's Sydney datacenter region.
- **`sdnotify`:** A Python package providing `sd_notify` integration via `$NOTIFY_SOCKET`.

## Architecture

### Target Topology

Single DigitalOcean Premium AMD droplet in Sydney (SYD1), 16 vCPU / 32 GB RAM (~$320/month, [DO pricing](https://www.digitalocean.com/pricing/droplets)). Three systemd units provide process isolation without network overhead:

```
DO Sydney (16 vCPU / 32 GB)
├── HAProxy              (TLS termination, /healthz routing)
├── promptgrimoire.service       (NiceGUI app, PgBouncer)
├── promptgrimoire-worker.service (LaTeX export, best-effort)
├── postgresql@16-main.service   (kernel-protected)
└── pgbouncer.service            (Unix socket pool)
        │
        │ WAL stream (TLS, async)
        ▼
NCI (existing VM, streaming replication standby)
```

**Why single machine, not multi-machine:** Production data shows the app uses ~4 GB at 196 concurrent users (Beszel, 2026-03-25) and PostgreSQL uses ~955 MB (systemd cgroup peak). Even at 2000 concurrent users (10× scaling target), projected memory is ~25 GB app + ~2 GB PG + ~3 GB worker headroom = ~30 GB, fitting in 32 GB. The 3-machine topology would cost ~$400/month for resource contention problems that systemd cgroup isolation solves at $320/month.

**Why move from NCI:** Current NCI Cloud costs $5–10k/quarter per VM. DigitalOcean at ~$320/month (~$960/quarter) is a 80–90% cost reduction for equivalent or better hardware.

**Australian data residency:** DO SYD1 is in Sydney, meeting the Australian data residency requirement ([DO regional availability](https://docs.digitalocean.com/platform/regional-availability/)).

### Process Isolation via systemd

Each service gets independent resource controls via systemd cgroup v2 ([systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)):

| Service | MemoryMax | OOMScoreAdjust | Nice | CPUWeight | IOSchedulingClass |
|---------|-----------|----------------|------|-----------|-------------------|
| `postgresql@16-main` | — | -1000 | 0 | 100 (default) | best-effort |
| `promptgrimoire` (app) | 24G (MemoryHigh=20G) | 0 | 0 | 100 (default) | best-effort |
| `promptgrimoire-worker` | 3G | 500 | 19 | 10 | idle |
| `pgbouncer` | 256M | -500 | 0 | 100 (default) | best-effort |

**Kernel kill order under memory pressure:** Worker (500) → App (0) → PgBouncer (-500) → PostgreSQL (-1000). The kernel OOM killer uses `OOMScoreAdjust` to select victims ([systemd.exec(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html), range -1000 to 1000, where -1000 disables OOM killing entirely).

**`MemoryMax` is a hard limit:** When breached, the kernel OOM killer targets the offending cgroup immediately ([systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)). The process is killed, not throttled. The app service pairs this with `MemoryHigh=20G` — a soft limit that applies kernel memory pressure (throttling) at 20 GB, giving a 4 GB warning zone of degraded performance before the hard kill at 24 GB. Users experience slowness instead of a sudden crash.

**`Nice=19`** gives the worker lowest CPU priority — it only gets CPU cycles when no other process wants them ([nice(1)](https://man7.org/linux/man-pages/man1/nice.1.html)).

**`IOSchedulingClass=idle`** means the worker only gets disk I/O when no other I/O is pending ([systemd.exec(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html), see also [ioprio_set(2)](https://man7.org/linux/man-pages/man2/ioprio_set.2.html)). LaTeX compilation may take longer under load, but the app and PG never notice.

**`CPUWeight=10`** (on a scale of 1–10000, default 100) gives the worker 1/10th the CPU share of default-weight processes under contention ([systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)).

### Connection Pooling: NullPool Behind PgBouncer

**Problem:** The current configuration runs SQLAlchemy's `QueuePool` (pool_size=80, max_overflow=15) behind PgBouncer in transaction mode. This is double-pooling — two layers of connection management that can interact pathologically:

- `pool_pre_ping=True` can cause `"unnamed prepared statement does not exist"` errors when PgBouncer reassigns the server connection between the ping and the actual query ([SQLAlchemy #10226](https://github.com/sqlalchemy/sqlalchemy/issues/10226)).
- SQLAlchemy's pool may become the bottleneck before PgBouncer's connection queuing can help — the app queues for one of its 80 slots while PgBouncer has idle server connections available.

**Fix:** Use `NullPool` when behind PgBouncer. Each `async with get_session()` opens a fresh connection through PgBouncer and closes it on exit. PgBouncer is the sole pool — connection queuing, thundering herd absorption, prepared statement management all in one place.

`NullPool` is explicitly documented as compatible with `create_async_engine()` ([SQLAlchemy pooling docs](https://docs.sqlalchemy.org/en/20/core/pooling.html)). SQLAlchemy maintainers recommend this pattern for external poolers ([SQLAlchemy discussion #10246](https://github.com/sqlalchemy/sqlalchemy/discussions/10246)).

**Configuration toggle:** New `DATABASE__USE_NULL_POOL` boolean (default `False`). Production sets it `True` via env. The existing `pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle` fields remain for non-PgBouncer environments (dev, CI). The test environment's `_PROMPTGRIMOIRE_USE_NULL_POOL=1` flag continues to work independently.

PgBouncer's `max_prepared_statements=200` (already deployed) handles asyncpg's protocol-level prepared statements transparently in transaction mode ([PgBouncer config docs](https://www.pgbouncer.org/config.html)).

### Export Worker as Standalone Service

**Current state:** `start_export_worker()` in `src/promptgrimoire/export/worker.py` runs as an `asyncio.Task` inside the NiceGUI process (spawned at app startup in `__init__.py:398`). It polls for jobs every 5 seconds, claims via `FOR UPDATE SKIP LOCKED`, and spawns `lualatex` subprocesses.

**Problem:** LaTeX subprocesses (up to 1.25 GB each, semaphore allows 2) share the app's cgroup. An OOM from LaTeX compilation kills the entire app, not just the export.

**Fix:** Move the worker to a separate systemd service with its own cgroup. The existing `start_export_worker()` coroutine is reusable — it just needs a standalone entry point that initializes the DB engine and runs the poll loop.

**Feature flag:** `FEATURES__WORKER_IN_PROCESS` (default `True`). When `True`, the app spawns the worker as an asyncio task (current behaviour — needed for dev, where `uv run run.py` starts everything). When `False` (production), the app does not spawn the worker; the separate systemd service runs it.

### Worker Monitoring

**systemd watchdog:** The worker service uses `Type=notify` with `WatchdogSec=300` ([systemd.service(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)). The worker calls `sd_notify("WATCHDOG=1")` on each poll cycle via the `sdnotify` Python package ([PyPI](https://pypi.org/project/sdnotify/)). If systemd doesn't receive a heartbeat within 5 minutes (longer than any reasonable compilation), it kills and restarts the process.

The asyncio event loop stays responsive during `compile_latex` (it uses `asyncio.create_subprocess_exec`, non-blocking), so the poll loop can keep sending heartbeats during long compiles. The only way the heartbeat stops is if the process is genuinely stuck or dead.

`sd_notify` protocol: communication via Unix domain socket at `$NOTIFY_SOCKET`. Key assignments: `READY=1` (startup complete), `WATCHDOG=1` (keepalive ping), `STOPPING=1` (graceful shutdown) ([sd_notify(3)](https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html)).

**Queue depth alert:** A cron job (or the worker itself, each poll cycle) checks `SELECT count(*) FROM export_job WHERE status IN ('queued', 'running')`. If >10, posts to the existing Discord webhook (`ALERTING__DISCORD_WEBHOOK_URL`). Same pattern as `deploy/check-pg-connections.sh`.

### Streaming Replication to NCI

NCI already runs PostgreSQL with the production data. After migration, flip NCI to a streaming replication standby:

- **Primary (DO):** `wal_level=replica` (default in PG 16+), `max_wal_senders=3`, `wal_keep_size=256MB` ([PG WAL config](https://www.postgresql.org/docs/current/runtime-config-wal.html))
- **Standby (NCI):** `standby.signal` file + `primary_conninfo` pointing at DO's public IP with `sslmode=verify-full` ([PG SSL docs](https://www.postgresql.org/docs/current/libpq-ssl.html))
- **Replication user:** Dedicated `replicator` role with `REPLICATION` attribute, authenticated via `scram-sha-256` over TLS
- **Base backup:** `pg_basebackup -h <DO_IP> -U replicator -D /var/lib/postgresql/16/standby -Fp -Xs -P` ([PG streaming replication](https://www.postgresql.org/docs/current/warm-standby.html))

**Monitoring:** `pg_stat_replication` view on primary shows `write_lag`, `flush_lag`, `replay_lag` per standby ([PG monitoring stats](https://www.postgresql.org/docs/current/monitoring-stats.html)). Cron check alerts Discord if `replay_lag` exceeds threshold.

**Failover (manual):** `SELECT pg_promote()` on standby, update PgBouncer config, restart app ([PG admin functions](https://www.postgresql.org/docs/current/functions-admin.html)). Automated failover is over-engineering for a megs-sized DB with nightly backups.

**Nightly backup continues:** `pg_dump -Fc` → rclone → SharePoint. Streaming replication protects against hardware failure; offsite backups protect against data corruption and accidental deletion. Different failure modes, both needed.

### Migration Sequence

**Pre-migration (48+ hours before):**
1. Lower DNS TTL to 60s on `grimoire.drbbs.org` (currently 3600s). Wait for caches to expire.
2. Provision DO droplet (16 vCPU / 32 GB, SYD1). Run deployment guide to completion.
3. Rehearsal: `pg_dump -Fc` on NCI → `pg_restore` on DO. Verify record counts.

**Cutover (~30 minutes):**
```
T-24h  Announcement: maintenance window at [time]
T+0    POST /api/pre-restart on NCI (flushes CRDT state, navigates users to /restarting)
T+1    HAProxy → maintenance mode (branded 503 with jittered reload)
T+2    systemctl stop promptgrimoire (app + in-process worker)
T+3    pg_dump -Fc on NCI (all CRDT state flushed and persisted, megs-sized DB, seconds)
T+4    pg_restore on DO
T+6    Verification: row counts per table, CRDT spot-check (3–5 workspaces)
T+9    Start app + worker on DO, wait for /healthz
T+11   Update DNS A record → DO droplet IP
T+12   HAProxy on DO → ready
T+16   Smoke test: login, open workspace, trigger export
T+21   Restore DNS TTL to 3600s
```

**Rollback:** If verification fails at T+5, don't start DO app. DNS stays on NCI. Resume NCI service. Old server kept running for 2× original TTL (2 hours) after successful cutover as warm standby, then configure as replication standby.

### Backup Strategy on DO

- **Nightly pg_dump → SharePoint** continues (adapted for local PG, no network hop)
- **DO automated backups:** Weekly snapshots of the full droplet (20% of droplet cost = ~$64/month, [DO backup pricing](https://www.digitalocean.com/pricing/backups))
- **VPC networking:** Free within SYD1 ([DO VPC pricing](https://docs.digitalocean.com/products/networking/vpc/details/pricing/))

### Cost Summary

| Item | Monthly Cost |
|------|-------------|
| DO Premium AMD 16 vCPU / 32 GB (SYD1) | ~$320 |
| DO weekly backups (20% of droplet) | ~$64 |
| NCI standby (existing allocation) | $0 incremental |
| **Total** | **~$384** |

vs. NCI current: $5–10k/quarter ($1,667–$3,333/month). **88–94% cost reduction.**

## Existing Patterns

**Worker architecture:** All three background workers (`export_worker.py`, `search_worker.py`, `deadline_worker.py`) follow the same polling-loop pattern: `while True` → claim work → process → `asyncio.sleep(interval)`. The export worker extraction reuses this pattern in a standalone process.

**Feature flags:** `FeaturesConfig` in `config.py` already has boolean toggles (`enable_roleplay`, `enable_file_upload`). Adding `worker_in_process` follows this pattern.

**Pool configuration:** `DatabaseConfig` in `config.py` already exposes pool settings via env vars (`DATABASE__POOL_SIZE`, etc.). Adding `DATABASE__USE_NULL_POOL` follows this pattern.

**systemd overrides:** Production already uses `systemctl edit promptgrimoire` for `MemoryMax=6G` and `OOMScoreAdjust=500`. The worker service follows this same approach.

**Discord alerting:** `deploy/check-pg-connections.sh` already implements the cron → query → Discord webhook pattern. Queue depth monitoring follows this exactly.

**NullPool in tests:** `engine.py` already has the `NullPool` code path (lines 179–181), toggled by `_PROMPTGRIMOIRE_USE_NULL_POOL`. The production NullPool toggle reuses this infrastructure.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Extract Export Worker to Standalone Process

**Goal:** The export worker can run as an independent process outside the NiceGUI app, with its own DB engine initialisation and signal handling.

**Components:**
- New entry point module `src/promptgrimoire/export/worker_main.py` — standalone `async def main()` that initialises the DB engine, runs the poll loop, and handles SIGTERM gracefully
- Feature flag `FEATURES__WORKER_IN_PROCESS` in `src/promptgrimoire/config.py` (FeaturesConfig) — default `True`
- Conditional worker startup in `src/promptgrimoire/__init__.py` — only spawn asyncio task when `worker_in_process` is `True`

**Dependencies:** None (first phase)

**Covers:** infra-split.AC1 (standalone worker), infra-split.AC7 (in-process dev mode)

**Done when:** `python -m promptgrimoire.export.worker_main` starts, polls for jobs, processes an export, and shuts down cleanly on SIGTERM. Setting `FEATURES__WORKER_IN_PROCESS=false` prevents the app from spawning the in-process worker. Tests verify both modes.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: NullPool Toggle

**Goal:** Production can use `NullPool` behind PgBouncer, eliminating double-pool pathology while retaining `QueuePool` for non-PgBouncer environments.

**Components:**
- New field `use_null_pool: bool = False` in `DatabaseConfig` (`src/promptgrimoire/config.py`)
- Updated pool selection logic in `init_db()` (`src/promptgrimoire/db/engine.py`) — when `use_null_pool` is `True`, use `NullPool` and skip pool_size/max_overflow/pool_pre_ping/pool_recycle. The existing `_PROMPTGRIMOIRE_USE_NULL_POOL` test path is preserved.

**Dependencies:** None (independent of Phase 1)

**Covers:** infra-split.AC2

**Done when:** `DATABASE__USE_NULL_POOL=true` causes the engine to use `NullPool`. Pool status logging adapts gracefully (NullPool has no `size()` method — `_pool_status()` already handles this). Tests verify both pool modes.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Worker systemd Watchdog Integration

**Goal:** The standalone worker sends `sd_notify` heartbeats so systemd can auto-restart on failure.

**Components:**
- `sdnotify` dependency in `pyproject.toml`
- Watchdog heartbeat in the poll loop (`src/promptgrimoire/export/worker_main.py`) — `READY=1` after init, `WATCHDOG=1` each poll cycle, `STOPPING=1` on shutdown
- systemd unit file `deploy/promptgrimoire-worker.service` with `Type=notify`, `WatchdogSec=300`, `Restart=on-watchdog`

**Dependencies:** Phase 1 (standalone worker exists)

**Covers:** infra-split.AC3

**Done when:** Worker sends heartbeats, systemd restarts it if heartbeat stops. Unit file includes all resource controls (`Nice=19`, `IOSchedulingClass=idle`, `MemoryMax=3G`, `OOMScoreAdjust=500`, `CPUWeight=10`).
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Queue Depth Monitoring

**Goal:** Discord alerts when the export queue exceeds 10 jobs.

**Components:**
- Monitoring script `deploy/check-export-queue.sh` — queries `export_job` table, posts Discord webhook if count >10. Same pattern as `deploy/check-pg-connections.sh`.
- Cron entry (every 2 minutes, matching PG connection check cadence)

**Dependencies:** None (independent, uses existing Discord webhook infrastructure)

**Covers:** infra-split.AC4

**Done when:** Queue depth >10 triggers a Discord alert with job count and oldest queued timestamp.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Deployment Guide Update

**Goal:** `docs/deployment.md` reflects the new single-machine topology with three systemd units.

**Components:**
- Updated `docs/deployment.md` — new section for worker service setup, resource controls for all three services, PgBouncer `NullPool` configuration, updated env var documentation
- Updated `deploy/restart.sh` — restart both `promptgrimoire` and `promptgrimoire-worker` services, with worker draining (finish current job before restart via `TimeoutStopSec=120`)
- systemd unit file for worker placed in `deploy/` for reference

**Dependencies:** Phases 1–4 (all code changes landed)

**Covers:** infra-split.AC5

**Done when:** A fresh deployer can follow the guide to set up the complete topology from scratch.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Streaming Replication to NCI

**Goal:** NCI runs as a hot standby receiving WAL from the DO primary.

**Components:**
- PostgreSQL configuration on DO primary (`wal_level`, `max_wal_senders`, `wal_keep_size`, `pg_hba.conf` for replication user)
- PostgreSQL configuration on NCI standby (`standby.signal`, `primary_conninfo` with `sslmode=verify-full`)
- Replication monitoring script `deploy/check-replication-lag.sh` — queries `pg_stat_replication`, alerts Discord if `replay_lag` exceeds threshold
- Documented failover procedure in `docs/deployment.md`

**Dependencies:** Phase 5 (deployment guide exists to document this)

**Covers:** infra-split.AC6

**Done when:** `pg_stat_replication` on DO shows NCI streaming with acceptable lag. Monitoring alerts if lag exceeds threshold.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Migration Execution

**Goal:** Production moves from NCI to DO with zero data loss and under 1 hour downtime.

**Components:**
- Migration checklist document `docs/migration-checklist.md` — step-by-step procedure with verification at each stage
- DNS TTL lowering (48 hours before)
- Rehearsal migration (pg_dump → pg_restore → verify)
- Cutover execution (maintenance mode → dump → restore → verify → start → DNS → smoke test)
- Rollback procedure

**Dependencies:** All previous phases (everything deployed and tested on DO before cutover)

**Covers:** infra-split.AC8, infra-split.AC9, infra-split.AC10

**Done when:** Production serves from DO, NCI is replication standby, DNS resolves to DO, smoke tests pass.
<!-- END_PHASE_7 -->

## Additional Considerations

**Worker drain on deploy:** `deploy/restart.sh` should give the worker time to finish a running compilation before killing it. Set `TimeoutStopSec=120` in the worker unit file (longer than the longest observed compilation of ~90 seconds). systemd sends SIGTERM first, waits 120 seconds, then SIGKILL.

**`MemoryHigh` as soft limit:** Consider setting `MemoryHigh=2.5G` on the worker in addition to `MemoryMax=3G`. This applies kernel memory pressure (throttling) before the hard kill, giving the compilation a chance to complete under memory pressure rather than being killed outright ([systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)).

**Semaphore reduction:** With `MemoryMax=3G`, the LaTeX semaphore should be reduced from 2 to 1 concurrent compilation (each can spike to 1.25 GB, two would exceed 3G including overhead). This is a configuration change, not a code change — the semaphore count should be configurable via env var.

**PgBouncer transaction mode limitations:** SET/RESET, LISTEN, session-level advisory locks, and WITH HOLD cursors are incompatible with transaction pooling ([PgBouncer features docs](https://www.pgbouncer.org/features.html)). The codebase does not use any of these features (verified by grep during brainstorming).

**Data residency:** DigitalOcean SYD1 servers are physically located in Sydney. MQ approval for DO hosting has been obtained. DO is a US company subject to CLOUD Act, but the university's data governance sign-off covers this.

**CRDT flush on cutover:** The existing `POST /api/pre-restart` endpoint (called by `deploy/restart.sh`) flushes Milkdown editor content to CRDT and persists all dirty CRDT state to database before shutdown. This ensures the final `pg_dump` captures all in-flight work. See `src/promptgrimoire/pages/restart.py`.

**Vertical resize as safety valve:** If the 2000 concurrent user target exceeds 32 GB (the 10× projection is untested), DO supports vertical droplet resize with a reboot (~5 minutes downtime). No code change required — just resize to 64 GB.
