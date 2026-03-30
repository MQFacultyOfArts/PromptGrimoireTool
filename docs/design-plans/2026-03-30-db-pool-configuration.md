# DB Connection Pool Configuration: NullPool → QueuePool Experiment

**Date:** 2026-03-30
**Status:** Proposed
**Author:** Claude (from telemetry analysis with Brian)
**Issue:** Connection churn, PgBouncer login timeouts, connection close cancellations

## Source Inventory

Single tarball: `telemetry-20260330-2157.tar.gz`, ingested into
`output/incident/incident.db`. No source duplication.

| Source | Format | Window (UTC) | Events | Timezone |
|--------|--------|-------------|--------|----------|
| structlog.jsonl (×6 rotated) | JSONL | 2026-03-30T10:06 – 10:57 | 172,985 | UTC |
| journal.json | journal | 2026-03-28T10:02 – 2026-03-30T10:57 | 221,729 | Aus/Syd |
| pgbouncer.log | pgbouncer | 2026-03-28T09:04 – 2026-03-30T10:57 | 840,096 | Aus/Syd |
| postgresql.log | pglog | within window | 966 | UTC |
| haproxy.log | haproxy | within window | 352,760 | Aus/Syd |

**JSONL limitation:** The six rotated JSONL files cycle rapidly under production load
and span only 51 minutes. Where the document cites app-side error counts, it uses the
**journal** (49-hour window), not JSONL. JSONL is used only for pool mode confirmation
(`INVALIDATE size=?` → NullPool).

**Server context:** DO server (`grimoire.drbbs.org`, 170.64.140.42). Has always run
NullPool — `DATABASE__USE_NULL_POOL=true` since initial deployment. There is no
QueuePool baseline from this server.

**Operational context:** The app was being killed by the memory watchdog throughout
the day (2026-03-30) as student traffic hit. The journal shows 57 `db_pool_mode`
events — 57 restarts in the 49-hour window.

**Positive controls:**
- Journal contains 57 `db_pool_mode` events, all `mode=NullPool reason=config`
- JSONL INVALIDATE events show `size=?` (NullPool has no pool size attribute)

**Command:**
```sql
SELECT count(*) FROM journal_events WHERE message LIKE '%db_pool_mode%'
-- Result: 57
```

## Findings

### Finding 1: NullPool generates ~8,400 PgBouncer connection cycles per hour

**Claim:** Every database operation creates a new PgBouncer connection and closes it
immediately, generating sustained connection churn.

**Evidence (PgBouncer log, 49 hours):**

| Metric | Count | Per Hour |
|--------|-------|----------|
| Login attempts | 413,997 | 8,449 |
| Client close requests | 413,159 | 8,432 |

**Commands:**
```sql
SELECT count(*) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%login attempt%'
-- Result: 413997

SELECT count(*) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%client close request%'
-- Result: 413159
```

The near-equal counts and PgBouncer's logged `age=0s` on all close events confirm
connections are created and destroyed per-query.

**Confidence:** Confirmed. PgBouncer logs directly measure the lifecycle.

### Finding 2: Connection close operations are cancelled at 18.5/hr

**Claim:** Connection close operations are being cancelled, producing
`Exception closing connection` errors. NullPool amplifies this because every request
closes its connection.

**Evidence (journal, 34.08 hours):**

| Metric | Count | Per Hour |
|--------|-------|----------|
| `Exception closing connection` | 629 | 18.46 |
| `INVALIDATE soft=False exception=CancelledError` | 3,261 | 88.67 |
| Close errors with NiceGUI Client in trace | 161 | — |

**Commands:**
```sql
SELECT count(*), min(ts_utc), max(ts_utc) FROM journal_events
WHERE message LIKE '%Exception closing connection%'
-- Result: 629, 2026-03-29T00:27:41Z – 2026-03-30T10:32:19Z (34.08h)

SELECT count(*), min(ts_utc), max(ts_utc) FROM journal_events
WHERE message LIKE '%INVALIDATE soft=False exception=CancelledError%'
-- Result: 3261, 2026-03-28T22:06:40Z – 2026-03-30T10:53:18Z (36.78h)

SELECT count(*) FROM journal_events
WHERE message LIKE '%Exception closing connection%'
  AND message LIKE '%nicegui.client.Client%'
-- Result: 161
```

**161 of 629** close errors (25.6%) include a NiceGUI Client object in the
CancelledError, confirming the NiceGUI task cancellation mechanism for those.
The remaining 468 (74.4%) are CancelledError without a Client object — the
cancellation source is not identified in those traces.

**Why QueuePool should reduce this:** QueuePool returns connections to the pool on
checkin — no `close()` call for normal requests. The close protocol runs only during
pool recycling (~1 per 30min per connection with `pool_recycle=1800`) and for overflow
connections (destroyed on return). This narrows the cancellation window but does not
eliminate it for overflow traffic.

**Confidence:** Confirmed for the close-error rate (629 events, journal). Confirmed
for the NiceGUI-cancellation path (161 events with stack trace). The remaining 468
close errors are confirmed as CancelledError but the cancellation source is unknown.

### Finding 3: PgBouncer login timeouts correlate with traffic peaks

**Claim:** Under NullPool, every query needs a fresh PgBouncer login handshake. When
the event loop is busy, the handshake stalls beyond PgBouncer's `client_login_timeout`
(15 seconds, per `docs/deployment.md:423`).

**Evidence (PgBouncer log, 49 hours):**

| Error | Count |
|-------|-------|
| `client_login_timeout` | 60 |
| `client sent partial pkt in startup phase` | 16 |
| `failed to send welcome message` | 2 |

**Commands:**
```sql
SELECT count(*) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%client_login_timeout%'
-- Result: 60

SELECT count(*) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%partial pkt%'
-- Result: 16
```

Timeouts cluster at high-traffic hours:

| Hour (UTC) | AEDT | Timeouts | Logins/hr |
|------------|------|----------|-----------|
| 2026-03-29T06 | 17:00 Sat | 18 | 13,627 |
| 2026-03-30T02 | 13:00 Mon | 16 | 21,503 |
| 2026-03-30T04 | 15:00 Mon | 12 | 15,498 |
| 2026-03-30T01 | 12:00 Mon | 6 | 24,216 |

**Command:**
```sql
SELECT substr(ts_utc, 1, 13) as hour, count(*) FROM timeline
WHERE source='pgbouncer' AND message LIKE '%client_login_timeout%'
GROUP BY hour ORDER BY hour
```

**Bridge to user-visible errors:** The expected path is: PgBouncer timeout → asyncpg
`TimeoutError` → `get_session()` catches as `Database session error, rolling back
transaction` (at `src/promptgrimoire/db/engine.py:328`) → Discord webhook. However,
the journal contains **0 rows** matching `Database session error, rolling back
transaction`:

```sql
SELECT count(*) FROM journal_events
WHERE message LIKE '%Database session error, rolling back transaction%'
-- Result: 0
```

This bridge is **inferred from code structure**, not confirmed from this dataset.
The Discord webhook alerts (~30 `Database session error` events) are out-of-band
evidence not present in the incident DB.

**Why QueuePool should eliminate this:** Persistent connections login once at creation.
The 8,449 handshakes/hour drop to ~20 per pool lifecycle event. No per-query handshake
means no window for event-loop-induced timeouts.

**Confidence:** Corroborated. Timeouts are confirmed in PgBouncer logs. Traffic
correlation is suggestive of event loop contention. The causal link to user-visible
errors is inferred, not confirmed from this dataset.

## Causal Chain

```
NullPool (DATABASE__USE_NULL_POOL=true, always on DO)
  │
  ├─→ Every DB query creates+destroys a PgBouncer connection
  │     (414k logins, 413k closes over 49h) [confirmed, pgbouncer]
  │
  ├─→ Under load, handshake competes with UI/WebSocket work
  │     │
  │     ├─→ PgBouncer client_login_timeout (60 events) [confirmed, pgbouncer]
  │     ├─→ PgBouncer partial pkt (16 events) [confirmed, pgbouncer]
  │     └─→ User-visible "Database session error" [inferred, 0 in journal]
  │
  └─→ Every request has a connection close in-flight
        │
        └─→ Task cancellation produces CancelledError on close
              (629 close errors, 3261 INVALIDATEs over ~35h) [confirmed, journal]
              ├─→ 161 traced to NiceGUI client disconnect [confirmed, journal]
              └─→ 468 cancellation source unidentified [observed, not attributed]
```

## Relationship to Prior Architecture Decision

The infra-split design (`docs/design-plans/2026-03-24-infra-split.md:140–153`) and
deployment guide (`docs/deployment.md:484–496`) justify NullPool as the fix for
double-pooling. Two QueuePool + PgBouncer failure modes are cited:

1. `pool_pre_ping=True` causes `unnamed prepared statement` errors when PgBouncer
   reassigns server connections between ping and query (SQLAlchemy #10226)
2. SQLAlchemy's pool bottlenecks before PgBouncer's queuing can help

**These concerns remain valid.** The infra-split design notes that
`max_prepared_statements=200` was already deployed at that time
(`docs/design-plans/2026-03-24-infra-split.md:153`), mitigating concern (1) for
asyncpg's protocol-level prepared statements, but not guaranteeing elimination.

**What this proposal adds:** NullPool has measured costs (414k connection cycles,
629 close errors, 60 login timeouts per 49h, 57 restarts from watchdog kills).
The question is whether QueuePool(20) + `pool_pre_ping=False` behind PgBouncer
produces fewer total errors than NullPool's per-query overhead.

**This is not a known answer.** The proposal is a controlled experiment with
specific regression signals and isolated variables (pool mode + pre_ping disabled
to avoid confounding).

## Current Configuration

### App

```
DATABASE__USE_NULL_POOL=true
# Defaults (unused): pool_size=80, max_overflow=15, pool_pre_ping=True, pool_recycle=3600
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

### PostgreSQL

```
max_connections = 120
statement_timeout = 30s
```

## Proposed Changes

### Scope

Affects both `promptgrimoire.service` and `promptgrimoire-worker.service` (same
`.env` at `deploy/promptgrimoire-worker.service:12`). Worker gets explicit override.

### 1. App `.env` (`/opt/promptgrimoire/.env`)

```diff
- DATABASE__USE_NULL_POOL=true
+ DATABASE__USE_NULL_POOL=false
+ DATABASE__POOL_SIZE=20
+ DATABASE__MAX_OVERFLOW=10
+ DATABASE__POOL_PRE_PING=false
+ DATABASE__POOL_RECYCLE=1800
```

**Rationale:**

- **`USE_NULL_POOL=false`**: Enables QueuePool. Persistent connections eliminate
  per-query handshake overhead.

- **`POOL_SIZE=20`**: 20 persistent connections for normal traffic. This is a
  deliberate tradeoff: demand between 21–30 concurrent DB operations uses overflow
  connections that are created and destroyed (still traversing the close path).
  Demand above 30 queues in SQLAlchemy while PgBouncer may still have spare server
  slots — this is the double-pooling bottleneck the original design warned about.
  Accepted as a tradeoff against the measured NullPool costs.

- **`MAX_OVERFLOW=10`**: Burst to 30. Overflow connections ARE destroyed on return
  and DO traverse the close path. This reduces close-cancellation to overflow-only
  traffic, not eliminates it entirely.

- **`POOL_PRE_PING=false`**: Explicitly disabled. The infra-split design warns that
  `pool_pre_ping=True` + PgBouncer transaction mode causes `unnamed prepared statement`
  errors (SQLAlchemy #10226). Disabling pre_ping isolates the experiment to one
  variable (pool mode) and avoids the documented hazard. PgBouncer handles connection
  health; the app doesn't need pre_ping.

- **`POOL_RECYCLE=1800`**: Recycle before PgBouncer's `server_lifetime` (3600s).

### 2. Worker systemd unit (`deploy/promptgrimoire-worker.service`)

```diff
  [Service]
  EnvironmentFile=/opt/promptgrimoire/.env
+ Environment=DATABASE__USE_NULL_POOL=true
```

Worker continues NullPool — single polling loop, one connection at a time.

### 3. PgBouncer

```diff
- default_pool_size = 80
+ default_pool_size = 40
```

App uses at most 30 connections. 40 provides headroom for burst + admin + worker.

### 4. PostgreSQL

No changes.

## Expected Outcomes (Hypotheses to Verify)

These are predictions to test against 24h post-deploy telemetry. If they don't hold,
the experiment has failed and we revert.

| Metric | Current (49h) | Expected | Source | Command |
|--------|--------------|----------|--------|---------|
| PgBouncer logins/hr | 8,449 | ~20 | pgbouncer | `timeline WHERE message LIKE '%login attempt%'` |
| `client_login_timeout` | 60 / 49h | 0 | pgbouncer | `timeline WHERE message LIKE '%client_login_timeout%'` |
| Close errors/hr | 18.46 | <2 | journal | `journal_events WHERE message LIKE '%Exception closing%'` |
| INVALIDATE/hr | 88.67 | <5 | journal | `journal_events WHERE message LIKE '%INVALIDATE%CancelledError%'` |
| `unnamed prepared statement` | 0 | 0 | journal | `journal_events WHERE message LIKE '%unnamed prepared statement%'` |

**If `unnamed prepared statement` errors appear**, revert immediately — that's the
double-pooling regression the original design warned about.

**If close errors don't decrease**, the cancellation source is not NullPool's
per-request close — investigate the 468 unattributed CancelledErrors separately.

## Deployment

**Precondition:** `deploy/restart.sh` may hang when DB connections are saturated.
Manual fallback included.

### Primary path

```bash
sudo vim /opt/promptgrimoire/.env
sudo systemctl edit promptgrimoire-worker  # Add Environment=DATABASE__USE_NULL_POOL=true
sudo vim /etc/pgbouncer/pgbouncer.ini
sudo systemctl reload pgbouncer
sudo bash /opt/promptgrimoire/deploy/restart.sh
```

### Fallback (if restart.sh hangs)

```bash
# Same config edits, then:
sudo systemctl restart promptgrimoire
sudo systemctl restart promptgrimoire-worker
sudo journalctl -u promptgrimoire --no-pager -n 20 | grep db_pool_mode
```

## Rollback

```bash
# .env: DATABASE__USE_NULL_POOL=true, remove POOL_SIZE/MAX_OVERFLOW/POOL_PRE_PING/POOL_RECYCLE
sudo vim /opt/promptgrimoire/.env
# PgBouncer: default_pool_size = 80
sudo vim /etc/pgbouncer/pgbouncer.ini
sudo systemctl reload pgbouncer
sudo systemctl restart promptgrimoire
```

## Not Addressed

- NiceGUI task cancellation root cause (architectural, separate from pool mode)
- Memory leak (#434)
- Telemetry collection gap (fixed: `collect-telemetry.sh` now collects worker journal)
- The 468 close errors without identified cancellation source
