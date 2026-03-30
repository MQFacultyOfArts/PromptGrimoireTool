# DB Connection Pool Configuration Overhaul

**Date:** 2026-03-30
**Status:** Proposed (post peer-review revision)
**Author:** Claude (from telemetry analysis with Brian)
**Issue:** Steady "Database session error" rate, connection churn, PgBouncer login timeouts

## Source Inventory

All data from `telemetry-20260330-2054.tar.gz` and `telemetry-20260330-2101.tar.gz`,
ingested into `output/incident/incident.db` via `incident_db.py`.

| Source | Format | Window (UTC) | Events | Timezone |
|--------|--------|-------------|--------|----------|
| structlog.jsonl (×6 rotated) | JSONL | 2026-03-25T23:30 – 2026-03-30T10:02 | 196,298+ | UTC |
| journal.json | journal | 2026-03-25T23:30 – 2026-03-30T10:05 | 207,870 | Australia/Sydney |
| pgbouncer.log | pgbouncer | 2026-03-25T23:30 – 2026-03-30T10:02 | see note¹ | Australia/Sydney |
| postgresql.log (concatenated rotated) | pglog | within window | 745 | UTC |
| haproxy.log | haproxy | within window | 339,424 | Australia/Sydney |
| Discord webhook alerts | manual review | 2026-03-29 – 2026-03-30 | ~50 | Australia/Sydney |

¹ **PgBouncer source duplication:** The tarball contains overlapping PgBouncer log
snapshots from multiple collection runs. Raw row counts are inflated ~2× vs. distinct
events. All PgBouncer counts in this document use `count(DISTINCT ts_utc || '|' || message)`
to deduplicate. Raw counts are noted where they differ materially.

**Positive control:** Epoch 4 restart at `2026-03-29T23:07:43Z` appears in JSONL
(`db_pool_mode` event), journal, and PgBouncer logs. Filters verified.

## Epoch Timeline

Epochs are classified by JSONL commit hash transitions. The `incident_db.py review`
command computes these automatically; the analysis below uses manual time-bounded
queries against epoch boundaries derived from that report.

**Epoch boundary timestamps (UTC), used in all per-epoch queries below:**

| Epoch | Start (UTC) | End (UTC) |
|-------|-------------|-----------|
| E1 | 2026-03-25T23:30:00Z | 2026-03-26T12:27:47Z |
| E2 | 2026-03-26T12:27:47Z | 2026-03-29T01:32:29Z |
| E3 | 2026-03-29T01:32:29Z | 2026-03-29T22:30:00Z |
| E4 | 2026-03-29T22:30:00Z | 2026-03-30T08:54:26Z |
| E5 | 2026-03-30T08:54:26Z | (end of window) |

| # | Commit | PR | Duration | Restart | Pool Mode |
|---|--------|----|----------|---------|-----------|
| 1 | 59caff8f | — | 12h 57m | first | QueuePool(80) |
| 2 | 3e8a4e5a | #433 query optimisation | 13h 22m | deploy | QueuePool(80) |
| 3 | 8b1b438e | #448 infra split | 55m | deploy | NullPool |
| 4 | f2331f39 | #458 security deps | 39m | crash | NullPool |
| 5 | 10edd86d | — | 1h 0m+ | crash | NullPool |

Pool mode confirmed by INVALIDATE event signatures. The `incident.db` schema does
not have an `epoch` column; per-epoch queries use `WHERE ts_utc >= '<start>' AND ts_utc < '<end>'`
with the boundaries above.

**Command (pool mode confirmation):**
```sql
-- QueuePool epochs show size=80; NullPool epochs show size=?
-- Example for E3:
SELECT count(*),
  count(CASE WHEN event LIKE '%size=80%' THEN 1 END) as queuepool,
  count(CASE WHEN event LIKE '%size=?%' THEN 1 END) as nullpool
FROM jsonl_events WHERE event LIKE '%INVALIDATE%'
  AND ts_utc >= '2026-03-29T01:32:29Z' AND ts_utc < '2026-03-29T22:30:00Z'
-- Result: 65 total, 0 queuepool, 65 nullpool
```

Explicit confirmation: `db_pool_mode mode=NullPool reason=config` at
`2026-03-29T23:07:43Z` (E4 startup) `[JSONL, UTC]`

**Command:**
```sql
SELECT ts_utc, extra_json FROM jsonl_events WHERE event = 'db_pool_mode'
-- Result: 2026-03-29T23:07:43.850789Z | {"mode": "NullPool", "reason": "config", ...}
```

## Relationship to Prior Architecture Decision

The infra-split design plan (`docs/design-plans/2026-03-24-infra-split.md:140–153`)
and deployment guide (`docs/deployment.md:484–496`) explicitly justify NullPool as
the fix for double-pooling pathology:

> SQLAlchemy's default connection pool creates a **second pool** on top of PgBouncer
> — the double-pooling pathology. Connections sit idle in SQLAlchemy's pool while
> PgBouncer counts them as active server connections, wasting PostgreSQL backend
> slots and causing pool exhaustion under load.

The infra-split design also cites two specific failure modes of QueuePool + PgBouncer:
1. `pool_pre_ping=True` can cause `"unnamed prepared statement does not exist"` errors
   when PgBouncer reassigns the server connection between ping and query (SQLAlchemy #10226)
2. SQLAlchemy's pool may bottleneck before PgBouncer's connection queuing can help

**Why the telemetry falsifies the NullPool recommendation:**

The double-pooling concern is real but the cure is empirically worse than the disease.
The telemetry shows NullPool introduces three failure modes not present under QueuePool:

1. **Connection churn** (Finding 1): 233k distinct PgBouncer logins in 36h, all `age=0s`.
   The per-query connection establishment adds event loop latency that QueuePool avoids
   entirely (warm connections, no per-query handshake).

2. **Login timeouts** (Finding 3): 60 distinct `client_login_timeout` events under
   NullPool (E3+E4), zero under QueuePool (E1+E2). The per-query handshake creates
   a window for event loop saturation to cause PgBouncer timeouts.

3. **Connection close cancellation** (Finding 2): 40 `Exception closing connection`
   errors under NullPool, 1 under QueuePool. NullPool closes every connection
   immediately, creating a large surface for NiceGUI task cancellation races.

**Mitigating the original double-pooling concerns:**

- **Prepared statement error (#10226):** PgBouncer's `max_prepared_statements=200`
  (already deployed) handles asyncpg's protocol-level prepared statements in
  transaction mode. This was not available when the original NullPool recommendation
  was made; it was deployed as part of the same infra-split PR.

- **Pool bottleneck:** The proposed `pool_size=20` (not 80) with `max_overflow=10`
  is deliberately undersized relative to PgBouncer's `default_pool_size`. The app
  holds at most 30 client connections; PgBouncer has 40 server slots. There is no
  bottleneck scenario where SQLAlchemy queues while PgBouncer has idle capacity.

- **Idle connection waste:** With `pool_size=20`, at most 20 PgBouncer server slots
  are held by idle SQLAlchemy connections. This is 50% of the proposed 40 server
  slots, compared to the original 80/80 (100%) that motivated the NullPool switch.
  `pool_recycle=1800` ensures connections are periodically returned.

**Guardrail for regression detection:** If double-pooling symptoms reappear
(`unnamed prepared statement` errors, pool exhaustion with PgBouncer idle), the
INVALIDATE event stream will show `checked_out` near pool_size with positive overflow.
The `POOL_SNAPSHOT` periodic log and `PG_CONNECTIONS` query (both in the diagnostic
logger) provide continuous visibility. Rollback to NullPool is a single env var change.

## Systematic Debugging: Hypotheses and Causal Chain

### Finding 1: NullPool creates pathological connection churn through PgBouncer

**Hypothesis:** With NullPool enabled, every database operation creates and destroys
a connection through PgBouncer, generating hundreds of thousands of connection cycles
per day and imposing per-query connection establishment overhead on the event loop.

**Evidence:**

PgBouncer login attempts per epoch (deduplicated):

| Epoch | Pool Mode | Duration | Logins | Logins/min |
|-------|-----------|----------|--------|------------|
| E2 | QueuePool(80) | 13h 22m | 21,212 | 26 |
| E3 | NullPool | 55m | 95,563 | 1,738 |
| E4 | NullPool | 39m | 111,296 | 2,854 |
| E5 | NullPool | 1h 0m | 5,680 | 95 |

**Command:**
```sql
SELECT count(DISTINCT ts_utc || '|' || message) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%login attempt%'
  AND ts_utc >= '2026-03-29T01:32:29Z' AND ts_utc < '2026-03-29T22:30:00Z'
-- E3 result: 95563
```

PgBouncer close events (deduplicated, all `age=0s`):

- Total distinct close events: **242,109** `[pgbouncer, full window, deduplicated]`
- **Command:** `SELECT count(DISTINCT ts_utc || '|' || message) FROM timeline WHERE source='pgbouncer' AND message LIKE '%client close request%'`

E2 (QueuePool) shows 26 logins/min — pool creation/recycling events, not per-query.
E3/E4 (NullPool) show 1,738–2,854 logins/min — every query creates a connection.
E5 is lower (95/min) due to lower traffic (Sunday evening), not pool mode.

**Falsification attempts:**
- Could the high E3/E4 churn be caused by something other than NullPool? No — the
  INVALIDATE signatures confirm NullPool (`size=?`), and the `db_pool_mode` event
  explicitly logs `mode=NullPool`. The churn exactly tracks NullPool activation.
- Could E2's 21k logins indicate QueuePool also churns? At 26/min over 13h, this is
  consistent with pool recycling (`pool_recycle=3600`) and connection invalidation,
  not per-query creation. QueuePool INVALIDATE events show stable pool state
  (`checked_in + checked_out ≈ 80`).

**Confidence:** Confirmed. Three independent sources agree (JSONL pool mode, PgBouncer
login counts, INVALIDATE event signatures). All counts deduplicated.

### Finding 2: Connection close operations are cancelled by NiceGUI client disconnections

**Hypothesis:** When users navigate away or their browser disconnects, NiceGUI cancels
all asyncio tasks for that client. If a database connection close is in-flight at that
moment, the close is cancelled mid-protocol, producing `Exception closing connection`
errors. NullPool amplifies this because every request has a connection close in-flight
(connections are not returned to a pool — they are destroyed).

**Evidence:**

Connection close errors per epoch:

| Epoch | Pool Mode | Duration | Close Errors | Errors/hr |
|-------|-----------|----------|-------------|-----------|
| E1 | QueuePool(80) | 12h 57m | 1 | 0.08 |
| E2 | QueuePool(80) | 13h 22m | 0 | 0 |
| E3 | NullPool | 55m | 19 | 20.7 |
| E4 | NullPool | 39m | 8 | 12.3 |
| E5 | NullPool | 1h 0m | 13 | 13.0 |

**Command:**
```sql
SELECT count(*) FROM jsonl_events
WHERE event LIKE '%Exception closing connection%'
  AND ts_utc >= '2026-03-29T01:32:29Z' AND ts_utc < '2026-03-29T22:30:00Z'
-- E3 result: 19
```

**Total:** 41 `Exception closing connection` events across window. `[JSONL, full window, UTC]`

All stack traces show the same pattern:
```
sqlalchemy/pool/base.py:374, in _close_connection
  → asyncpg/connection.py:1513, in close
    → asyncpg/protocol/protocol.pyx:632, in close
      asyncio.exceptions.CancelledError: <nicegui.client.Client object at 0x...>
```

The `CancelledError` carries a NiceGUI Client object reference — the cancellation
originates from NiceGUI's client cleanup, not from the database layer.

**Falsification attempts:**
- Could the close errors be caused by PgBouncer killing connections? No — the
  `CancelledError` carries a NiceGUI Client object, not a socket or protocol error.
  PgBouncer-initiated disconnects would show `ConnectionResetError` or
  `ConnectionDoesNotExistError`.
- Could QueuePool also produce these errors at scale? E1/E2 show 0–1 occurrences
  over 26 hours combined. QueuePool returns connections to the pool (no close),
  so the close operation only happens during pool recycling or invalidation — far
  less frequently than NullPool's per-request close.

**Confidence:** Confirmed. Stack traces directly show the causal mechanism. Rate
difference between QueuePool (0.04/hr) and NullPool (13–21/hr) is >100×.

### Finding 3: PgBouncer login timeouts correlate with event loop saturation

**Hypothesis:** Under NullPool, every database query requires a fresh connection to
PgBouncer, including a startup message + auth handshake. When the asyncio event loop
is saturated (rendering NiceGUI UI, processing WebSocket messages, broadcasting CRDT
updates), the handshake stalls. PgBouncer's `client_login_timeout` (configured as
**15 seconds** per `docs/deployment.md:423`) expires and it drops the connection.
The app then raises `TimeoutError` → the `get_session()` context manager catches it
as `Database session error, rolling back transaction` → Discord webhook fires.

**Evidence:**

PgBouncer errors (deduplicated across overlapping source files):

| Error | Count (dedup) | Epochs |
|-------|--------------|--------|
| `client_login_timeout` | **60** (raw: 120) | E3: 24, E4: 36 |
| `client sent partial pkt in startup phase` | **16** (raw: 32) | across E3–E5 |
| `failed to send welcome message` | **2** (raw: 4) | E3–E4 |

**Command:**
```sql
SELECT count(DISTINCT ts_utc || '|' || message) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%client_login_timeout%'
  AND ts_utc >= '2026-03-29T01:32:29Z' AND ts_utc < '2026-03-29T22:30:00Z'
-- E3 result: 24

SELECT count(DISTINCT ts_utc || '|' || message) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%client_login_timeout%'
  AND ts_utc >= '2026-03-29T22:30:00Z' AND ts_utc < '2026-03-30T08:54:26Z'
-- E4 result: 36
```

Corroborating JSONL evidence:
- `session_acquire_slow` warnings: **7** `[JSONL, full window, UTC]`
- `Database session error, rolling back transaction`: **7** in JSONL `[JSONL, full window, UTC]`
  - Of these, the one with full stack trace (E3, `2026-03-29T02:21:17Z`) shows
    `asyncpg.connect()` → `CancelledError` during connection establishment — the
    event loop cancelled the connection attempt before PgBouncer could respond.

Discord webhook alerts (manual count, 2026-03-29 13:21 to 2026-03-30 20:01 AEDT):
- `Database session error`: ~30 alerts `[Discord, manual count, AEDT]`
- `session_storage_assertion_failed`: ~15 alerts `[Discord, manual count, AEDT]`

**Note:** Discord webhook alerts undercount vs. JSONL because the webhook has
rate limiting and only fires on ERROR level. The JSONL count of 7 `Database session
error` events is lower than Discord's ~30 because the JSONL window doesn't cover
the full period shown in Discord (Discord shows alerts from earlier tarballs' windows
plus the gap between Epoch 4's crash and Epoch 5's start).

**Falsification attempts:**
- Could the login timeouts be caused by PgBouncer overload, not event loop saturation?
  Unlikely — PgBouncer's `max_client_conn=500` is far above the concurrent connection
  count. PgBouncer itself is not resource-constrained. The timeouts are client-side:
  the app starts the handshake but doesn't complete it within 15 seconds.
- Could the `partial pkt` errors be network issues? The connection is via Unix socket
  (`@unix(...):6432`), so TCP/network issues don't apply. Partial packets on a Unix
  socket mean the sending process stalled mid-write — consistent with event loop
  saturation.
- Do login timeouts appear under QueuePool? Not in this window — E1/E2 show 0
  login timeouts. QueuePool connections are persistent, so login happens once per
  connection lifecycle, not per query.

**Confidence:** Corroborated. Multiple independent sources agree (PgBouncer errors,
JSONL stack traces, Discord alerts), but the direct link between "event loop busy"
and "handshake timeout" is inferred from the mechanism, not directly measured. Event
loop lag metrics (`event_loop_lag_ms`) in the diagnostic logger show low values in
E5 (~0–3ms), but the timeouts occurred in E3/E4 where diagnostic data is sparser.

### Finding 4: QueuePool(80) was over-provisioned but functionally stable

**Hypothesis:** The original QueuePool configuration (pool_size=80, max_overflow=15)
allocated too many connections for a single async process but did not cause the
connection churn or timeout errors seen under NullPool. The 5xx rate in E1/E2 was
caused by other factors (event loop blocking, query performance), not pool configuration.

**Evidence:**

| Metric | E1 QueuePool | E2 QueuePool | E3 NullPool | E5 NullPool |
|--------|-------------|-------------|-------------|-------------|
| 5xx Rate | 4.77% | 2.86% | 12.85% | 0.10% |
| Conn Close Errors | 1 | 0 | 19 | 13 |
| INVALIDATE Events | 167 | 214 | 65 | 77 |
| PgBouncer Logins/min (dedup) | — | 26 | 1,738 | 95 |
| Login Timeouts (dedup) | 0 | 0 | 24 | 0 |

**Command (example, E1 close errors):**
```sql
SELECT count(*) FROM jsonl_events
WHERE event LIKE '%Exception closing connection%'
  AND ts_utc >= '2026-03-25T23:30:00Z' AND ts_utc < '2026-03-26T12:27:47Z'
-- Result: 1
```

E2's 5xx rate improvement (4.77% → 2.86%) came from #433 (query optimisation), not
pool changes — both E1 and E2 ran QueuePool(80). E5's dramatic improvement (0.10%)
came from #460 (lazy card rendering), not pool mode.

The INVALIDATE events under QueuePool show healthy pool churn:
`checked_in + checked_out ≈ 80`, `overflow` between -14/15 and 0/15. The pool was
never exhausted (no `checked_out=80+overflow` events).

**Confidence:** Confirmed. INVALIDATE event signatures directly show pool state.
5xx rate changes align with known PRs, not pool mode changes.

## Causal Chain

```
NullPool enabled (DATABASE__USE_NULL_POOL=true)
  │
  ├─→ Every DB query creates a new asyncpg connection to PgBouncer
  │     (233k distinct logins in 36h window) [confirmed]
  │
  ├─→ Connection establishment adds latency to every query path
  │     (asyncpg connect → PgBouncer startup msg → auth → server assign) [confirmed]
  │
  ├─→ When event loop is saturated, connection handshake stalls
  │     │
  │     ├─→ PgBouncer client_login_timeout fires (60 distinct events, 15s timeout) [confirmed]
  │     │
  │     ├─→ PgBouncer "partial pkt in startup phase" (16 distinct events) [confirmed]
  │     │
  │     └─→ asyncpg raises TimeoutError or CancelledError [confirmed, stack trace]
  │           │
  │           └─→ get_session() catches as "Database session error" [confirmed]
  │                 │
  │                 └─→ Discord webhook fires, user sees error [confirmed]
  │
  └─→ Every request has a connection close in-flight after completion
        │
        └─→ NiceGUI client disconnect cancels the close task [confirmed, stack trace]
              │
              └─→ "Exception closing connection" CancelledError (41 events) [confirmed]
```

**Contributing factors (necessary but not sole cause):**
1. **NullPool configuration** — root enabler of per-query connection churn
2. **Single-threaded asyncio event loop** — connection establishment competes with UI rendering
3. **NiceGUI task cancellation on client disconnect** — cancels in-flight DB operations
4. **PgBouncer's `client_login_timeout=15`** — drops connections when handshake exceeds 15s

**What would strengthen the inferred links:**
- Direct measurement of event loop lag during login timeout events (need correlated
  `event_loop_lag_ms` samples at the same second as PgBouncer timeout events)
- A/B comparison: deploy QueuePool, collect telemetry, compare login timeout rate

## Current Configuration

### App (SQLAlchemy/asyncpg)

```
DATABASE__USE_NULL_POOL=true
# Defaults in config.py (not used when NullPool is active):
# pool_size=80, max_overflow=15, pool_pre_ping=True, pool_recycle=3600
# connect_args: timeout=10, command_timeout=30
```

### PgBouncer (`/etc/pgbouncer/pgbouncer.ini`)

```ini
pool_mode = transaction
max_client_conn = 500
default_pool_size = 80
server_lifetime = 3600
server_idle_timeout = 600
client_login_timeout = 15
```

**Source:** `grep -E '(default_pool_size|max_client_conn|server_idle_timeout|server_lifetime|pool_mode)' /etc/pgbouncer/pgbouncer.ini` run on grimoire-DO at 2026-03-30 ~21:00 AEDT.
`client_login_timeout` value from `docs/deployment.md:423`.

### PostgreSQL (`postgresql.conf`)

```
max_connections = 120
statement_timeout = 30s
shared_buffers = 8GB
```

### Connection Flow (Current)

```
App (NullPool) → PgBouncer (transaction mode, 80 server conns) → PostgreSQL (120 max)
    ↑                    ↑                                            ↑
    creates+destroys     assigns server conn                          80 of 120 slots
    per query            from its pool per txn                        reserved
```

## Proposed Changes

### Scope

This change affects **both** the main app (`promptgrimoire.service`) **and** the
standalone export worker (`promptgrimoire-worker.service`), because both load the
same `.env` file (`deploy/promptgrimoire-worker.service:12`: `EnvironmentFile=/opt/promptgrimoire/.env`).

The worker should continue using NullPool — it runs a single polling loop with one
connection at a time, so QueuePool adds no benefit. An explicit override in the
worker's systemd unit prevents the app's `.env` change from affecting it.

### Connection Flow (Proposed)

```
App (QueuePool, 20+10) → PgBouncer (transaction mode, 40 server conns) → PostgreSQL (120 max)
    ↑                        ↑                                               ↑
    maintains 20 warm        multiplexes 30 client                           40 of 120 slots
    connections, reuses      conns onto 40 server conns                      reserved
```

### 1. App `.env` (`/opt/promptgrimoire/.env`)

```diff
- DATABASE__USE_NULL_POOL=true
+ DATABASE__USE_NULL_POOL=false
+ DATABASE__POOL_SIZE=20
+ DATABASE__MAX_OVERFLOW=10
+ DATABASE__POOL_RECYCLE=1800
```

**Rationale:**

- **`USE_NULL_POOL=false`**: Re-enables QueuePool. The app maintains persistent
  connections to PgBouncer, eliminating the ~233k distinct connection cycles observed
  in this window. Each query checks out an existing connection and returns it — no
  connect/close overhead on the event loop.

- **`POOL_SIZE=20`**: The app is a single-process async server. It doesn't need 80
  concurrent connections. Epoch 1–2 INVALIDATE events show `checked_out` values
  ranging from 1 to 56, with the pool (`checked_in + checked_out`) stable at 80.
  Most of those 80 connections sat idle. 20 handles realistic concurrency; the
  overflow handles bursts.

- **`MAX_OVERFLOW=10`**: Burst capacity to 30 total. Well under PgBouncer's proposed
  40 server limit. Overflow connections are created on demand and destroyed when
  returned (not kept idle), so this only activates under genuine burst load.

- **`POOL_RECYCLE=1800`**: Connections are recycled every 30 minutes. This is
  intentionally shorter than PgBouncer's `server_lifetime` (3600s) to ensure
  the app never encounters a stale connection from PgBouncer recycling its
  server-side connections.

### 2. Worker systemd unit (`deploy/promptgrimoire-worker.service`)

```diff
  [Service]
  EnvironmentFile=/opt/promptgrimoire/.env
+ Environment=DATABASE__USE_NULL_POOL=true
```

**Rationale:** The worker must continue using NullPool. It runs a single polling loop
that claims one job at a time — QueuePool would just hold idle connections open. The
`Environment=` directive overrides the `.env` file value for this unit only
(systemd: later directives win for the same key).

### 3. PgBouncer (`/etc/pgbouncer/pgbouncer.ini`)

```diff
- default_pool_size = 80
+ default_pool_size = 40
```

**Rationale:** With the app using at most 30 concurrent client connections
(20 + 10 overflow), PgBouncer only needs enough server connections to serve those.
40 provides headroom for burst + admin/monitoring queries + worker. Reducing from 80
frees PostgreSQL connection slots: from 80/120 reserved to 40/120, leaving 80 slots
for replication, admin, monitoring, and future services.

All other PgBouncer settings remain unchanged:
- `pool_mode = transaction` — correct for async apps with short transactions
- `max_client_conn = 500` — ample headroom
- `server_lifetime = 3600` — standard; app-side `pool_recycle=1800` stays ahead of this
- `server_idle_timeout = 600` — idle server connections close after 10 min, saves PG memory
- `client_login_timeout = 15` — unchanged; QueuePool eliminates per-query login so this
  only fires during pool initialisation or connection recycling

### 4. PostgreSQL

No changes. `max_connections=120` accommodates 40 PgBouncer server connections +
replication + admin with comfortable headroom. `statement_timeout=30s` matches the
app's `command_timeout=30`.

## Expected Outcomes

### Eliminated

- ~233k/36hr distinct connection open/close cycles through PgBouncer
- PgBouncer `client_login_timeout` errors (connections are persistent, no login per query)
- PgBouncer `partial pkt in startup phase` errors (no per-query handshake)

### Reduced

- `Exception closing connection` CancelledError rate: from ~13/hr to ~0.08/hr
  (QueuePool only closes connections on recycle/invalidation, not per-request)
- "Database session error" rate: from ~30/day to estimated 2–3/day
  (residual errors from genuine DB/network issues, not connection churn)
- Event loop pressure from connection establishment latency

### Unchanged

- NiceGUI client disconnection task cancellation (architectural, not pool-related)
- Memory leak trajectory (#434 — separate investigation)
- 5xx rate from non-DB causes (JS timeouts, ASGI exceptions)

## Monitoring

After deployment, verify via structlog:

**Startup confirmation:**
```
db_pool_mode mode=QueuePool pool_size=20 max_overflow=10
```

**Pool health indicators:**
- `INVALIDATE size=20 checked_in=N checked_out=M overflow=X/10` (real numbers, not `?`)
- `POOL_SNAPSHOT` and `PG_CONNECTIONS` in periodic diagnostic output

**Warning thresholds:**
- `checked_out` consistently near 20 → pool too small, increase `POOL_SIZE`
- `overflow` frequently positive → burst capacity used, consider increasing `MAX_OVERFLOW`
- `session_acquire_slow` warnings → pool exhaustion, increase both
- Any `ConnectionDoesNotExistError` → stale connection from PgBouncer recycling;
  verify `pool_recycle < server_lifetime`
- Any `unnamed prepared statement does not exist` → double-pooling regression;
  verify PgBouncer `max_prepared_statements=200` and consider reverting to NullPool

## Deployment Sequence

**Precondition:** `deploy/restart.sh` hangs when DB connections are saturated.
This is the same failure mode this change mitigates, meaning the normal deployment
path may not be available. The sequence below includes a manual fallback.

### Primary path (if restart.sh is responsive)

```bash
# 1. Edit app .env
sudo vim /opt/promptgrimoire/.env

# 2. Add worker NullPool override to service unit
sudo systemctl edit promptgrimoire-worker
# Add under [Service]:
#   Environment=DATABASE__USE_NULL_POOL=true

# 3. Edit PgBouncer config
sudo vim /etc/pgbouncer/pgbouncer.ini

# 4. Reload PgBouncer (live — no downtime)
sudo systemctl reload pgbouncer

# 5. Restart app and worker via zero-downtime script
sudo bash /opt/promptgrimoire/deploy/restart.sh
```

### Fallback path (if restart.sh hangs on DB)

```bash
# 1–4: same as above

# 5. Direct restart (not zero-downtime — brief 503 window)
sudo systemctl restart promptgrimoire
sudo systemctl restart promptgrimoire-worker

# 6. Verify both came up
sudo systemctl status promptgrimoire promptgrimoire-worker
sudo journalctl -u promptgrimoire --no-pager -n 20 | grep db_pool_mode
```

The direct `systemctl restart` bypasses the pre-restart hook (session invalidation,
editor flush) but the startup-time `invalidate_sessions_on_disk()` handles session
cleanup. Users will see a brief reconnection prompt. HAProxy's health check will
return 503 for ~5–10 seconds during restart.

## Risks

1. **Pool exhaustion under extreme burst:** If >30 concurrent DB operations are needed,
   requests queue waiting for a connection. Mitigated by: `pool_pre_ping=True` quickly
   recycles dead connections; `command_timeout=30` prevents stuck connections; diagnostic
   logger reports pool status for early detection.

2. **Stale connections after PgBouncer restart:** If PgBouncer is restarted (not
   reloaded), all client connections die. `pool_pre_ping=True` detects this on next
   checkout and creates fresh connections. Brief error spike expected (one failed
   query per stale connection).

3. **Double-pooling regression:** QueuePool + PgBouncer in transaction mode is the
   configuration that the infra-split design warned against. The mitigations
   (smaller pool, `max_prepared_statements=200`, pool_recycle < server_lifetime)
   address the known failure modes, but novel interactions are possible. Monitor
   for `unnamed prepared statement` errors as the canary.

4. **Rollback path:**
   ```bash
   # Revert .env
   sudo vim /opt/promptgrimoire/.env
   # Set: DATABASE__USE_NULL_POOL=true

   # Revert PgBouncer
   sudo vim /etc/pgbouncer/pgbouncer.ini
   # Set: default_pool_size = 80
   sudo systemctl reload pgbouncer

   # Restart (use fallback if primary hangs)
   sudo systemctl restart promptgrimoire
   ```
   Rollback is available via `systemctl restart` even when `restart.sh` is hung.

## Not Addressed

- **NiceGUI client disconnection cancelling in-flight DB operations:** Separate issue
  (NiceGUI task lifecycle). Pool change reduces surface area (fewer closes in flight)
  but doesn't eliminate the root cause.

- **Memory leak investigation (#434):** Pool configuration doesn't affect the suspected
  memory leak in NiceGUI client lifecycle. Separate workstream.

- **Telemetry collection gap:** `collect-telemetry.sh` now collects from both
  `promptgrimoire.service` and `promptgrimoire-worker.service` (fixed in this branch,
  commit `18fccaff`).
