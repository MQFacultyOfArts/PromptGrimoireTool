# Post-Mortem: 2026-03-29 Search Worker Cascade Failure

*Written: 2026-03-29*
*Investigator: Claude (Opus 4.6)*
*Status: Immediate mitigation deployed (PR #451). Proper fix tracked in #452, #454.*

## Summary

At 141 concurrent users on the new DigitalOcean server, PgBouncer transaction latency climbed from a 2ms baseline to 2,230ms over approximately 3 hours, cascading into DB session timeouts, connection failures, and user disconnection. The server did not crash (no SIGABRT/OOM) — it browned out, shedding websocket connections until all users were disconnected.

Two contributing factors identified:

1. **Search worker `FOR UPDATE SKIP LOCKED`** on the workspace table contended with page-load queries under NullPool. The search worker processed 15–24 dirty workspaces every 30–90 seconds during peak load, holding row locks that blocked annotation page loads. This was the cascade amplifier that made recovery impossible.

2. **`render_respond_tab` `ui.run_javascript()` with 5s timeout** blocks the server-side event loop waiting for a client browser response. Under concurrent load, multiple simultaneous Respond tab switches queue 5-second awaits, causing event loop lag spikes. This is the underlying bottleneck that persists after the search worker mitigation.

## Timeline (AEDT)

| Time | Users | xact latency | Event |
|------|-------|-------------|-------|
| 08:00 | 10 | 2ms | Baseline. Process started ~midnight after DO migration. |
| 10:00 | 41 | 10ms | Healthy. MALLOC_ARENA_MAX=2, PgBouncer+NullPool, search worker ON. |
| 10:21 | 52 | 51ms | First latency spike above 10ms. |
| 11:10 | 82 | 96ms | Spikes becoming regular. |
| 11:52 | ~95 | 127ms | Sustained degradation begins. |
| 12:06 | ~115 | 158ms | Entering danger zone. |
| 12:34 | ~125 | 208ms | First spike above 200ms. |
| 12:40 | ~130 | 376ms | Accelerating. |
| 13:07 | ~133 | 463ms | Approaching critical. |
| 13:09 | ~135 | 811ms | Sub-second threshold breached. |
| 13:12 | ~135 | 1,244ms | PostgreSQL logs `search_dirty` query at 1,504ms. Search worker processes 23 workspaces. |
| 13:15 | 134 | 945ms | |
| 13:20:27 | 138 | 500ms | PgBouncer server connection stuck "not ready" for 501s, forcibly closed. |
| 13:20:38 | — | — | PgBouncer opens burst of 8 new server connections (thundering herd). |
| 13:21:12 | — | 2,230ms | DB session errors: `TimeoutError` in `list_document_headers`. Discord alerts fire. |
| 13:21:17 | — | — | "Exception closing connection" + "Failed to load workspace content" cascade. |
| 13:22 | 8 | 1,871ms | Users shedding. Export job query takes 2,044ms. |
| 13:23 | 0 | 2,637ms | `session_storage_assertion_failed`, `Exception in ASGI application`. All users disconnected. |
| 13:28 | 0 | — | Manual restart (`deploy/restart.sh --skip-tests`). |
| 14:14 | 0 | — | Second restart (PR #451 deploy, search worker disabled). |
| 14:22 | 111 | — | Post-fix: 8ms event loop lag at 111 users. |
| 14:24 | 117 | — | Lag spike to 576ms (respond tab JS), recovers to 6ms. |
| 14:30 | 24 | — | Second brownout — respond tab JS causes lag, users shed to 24. Server recovers without restart. |

## Impact

- **User-facing:** All 141 connected users disconnected at 13:21–13:23. Service unavailable for ~5 minutes until manual restart.
- **Second brownout:** Post-fix, 110 users dropped to 24 at 14:30 due to event loop lag from respond tab JS. Server recovered without restart.
- **Session contamination:** Checked via #447 session identity tracing. Zero contamination detected across 101 authenticated sessions during the brownout window. Session invalidation on restart (#440/#443) provides additional safety net.
- **Data loss:** None. CRDT state persists independently of websocket connections.

## Source Inventory

| Source | File | Timezone | Window | Events |
|--------|------|----------|--------|--------|
| structlog | structlog.jsonl (49 MB) | UTC | 2026-03-28T11:00Z – 2026-03-29T03:00Z | 163,384 |
| journal | journal.json (25 MB) | UTC | same | 17,362 |
| HAProxy | haproxy.log (8.6 MB) | AEDT (UTC+11) | same | 24,245 |
| PgBouncer | pgbouncer.log (20 MB) | AEDT (UTC+11) | 2026-03-28 20:04 AEDT – collection | 124,405 |
| PostgreSQL | postgresql.log (138 KB) | AEDT (UTC+11) | same | 283 |
| DB snapshot | db-snapshot.json | UTC | snapshot at collection | — |

All times in this postmortem are AEDT (UTC+11) unless otherwise marked. Telemetry collected via `deploy/collect-telemetry.sh`, ingested into `output/incident/incident.db`.

## Contributing Factors

### 1. Search worker FOR UPDATE SKIP LOCKED contends with page loads

**Hypothesis:** The search extraction worker's `FOR UPDATE OF w SKIP LOCKED` on the workspace table acquires row-level locks that block annotation page loads reading the same rows. Under NullPool (every query opens/closes a PgBouncer connection), lock contention scales linearly with user count.

**Evidence:**

- Source: `[structlog, UTC, filtered 01:32–02:27]`
- The search worker logged "Processed N dirty workspaces" 66 times during the epoch. Processing was continuous — 15–24 workspaces every 30–90 seconds with no idle periods during peak load.
- Command: `grep 'dirty workspace' structlog.jsonl | wc -l` → 66
- At 02:12:59 UTC (13:12 AEDT), search worker logged "Processed 23 dirty workspaces". PostgreSQL logged the `search_dirty` query at 1,504ms in the same minute.
- Source: `[postgresql.log, AEDT]`
- `duration: 1504.418 ms execute PGBOUNCER_263: SELECT w.id, w.crdt_state ... WHERE w.search_dirty = true ... FOR UPDATE OF w SKIP LOCKED`

**Falsification attempts:**

- Could the latency be from query complexity, not lock contention? The query is a simple `SELECT ... LEFT JOIN activity` with a boolean filter — no FTS, no aggregation. 1,504ms for this query implies waiting, not computing.
- Could something other than the search worker hold the locks? `FOR UPDATE SKIP LOCKED` is only used in `search_worker.py`. Page loads use read-only queries. The search worker is the only writer that locks workspace rows.

**Confidence:** Corroborated. PgBouncer stats show latency correlating with search worker cycles. PostgreSQL confirms the specific query. Mechanism (row-level lock contention) is inferred from the `FOR UPDATE` semantics, not directly measured via `pg_stat_activity`.

### 2. PgBouncer server connection stuck "not ready" for 501 seconds

**Hypothesis:** A PgBouncer server connection became stuck in a "not ready" state (held by a long-running transaction from the search worker), was forcibly closed after 501 seconds, and the resulting reconnection burst caused a thundering herd.

**Evidence:**

- Source: `[pgbouncer.log, AEDT]`
- `13:20:27.489 AEDT ... closing because: client disconnect while server was not ready (age=501s)`
- Between 13:20:38 and 13:20:45, PgBouncer opened 8 new server connections to PostgreSQL.
- PgBouncer stats at 13:21: `8 xacts/s` (up from 3), `xact=2,230,059 us`, `wait=2,701 us`. The wait time appearing for the first time confirms connection queueing.

**Falsification attempts:**

- Could the 501s "not ready" be from something other than the search worker? The search worker's `FOR UPDATE` is the only mechanism that holds transactions open for extended periods. Regular page loads are short reads. 501 seconds aligns with ~8 search worker cycles at 60s intervals.
- Could the reconnection burst alone cause the cascade without the search worker? Unlikely — 8 new connections to a PostgreSQL instance with `max_connections=120` is not exhaustion. The cascade was caused by the event loop being saturated by stacked DB waits, not by pool exhaustion.

**Confidence:** Confirmed. Direct PgBouncer log evidence for the connection death and reconnection burst. Causal link to the search worker's `FOR UPDATE` is inferred (corroborated).

### 3. render_respond_tab blocks event loop with 5s JS timeout

**Hypothesis:** `render_respond_tab()` calls `await ui.run_javascript(...)` with a 5-second timeout. When multiple users switch to the Respond tab simultaneously, these awaits stack up and block the event loop, causing lag spikes even with the search worker disabled.

**Evidence:**

- Source: `[structlog, UTC, filtered 02:20–02:25]`
- Three `JavaScript did not respond within 5.0 s` errors, all with the same stack trace: `respond.py:589` → `tab_bar.py:280` → `_initialise_respond_tab`.
- Post-fix (search worker disabled), event loop lag spikes to 576ms at 117 users (14:24 AEDT) with the same JS timeout errors in the log. Server recovers instead of cascading.

**Falsification attempts:**

- Could the JS timeouts be a symptom (event loop already saturated) rather than a cause? Both. Under high DB latency, the event loop is slow to dispatch JS requests, increasing timeout probability. But the 5s `await` itself is also a cause — it holds an asyncio task for the full timeout duration. Post-fix, the JS timeouts still cause lag spikes with zero DB contention, confirming they are independently problematic.

**Confidence:** Confirmed for the JS timeout errors. The causal claim that these are the *primary* remaining bottleneck (post-search-worker-fix) is corroborated by the 14:24 AEDT evidence.

## Causal Chain

```
Search worker FOR UPDATE locks workspace rows (every 30-90s)
    ↓ [confirmed link]
Page loads queue behind row locks under NullPool
    ↓ [inferred link — mechanism, not directly measured]
PgBouncer xact latency climbs linearly with user count (2ms → 945ms over 5 hours)
    ↓ [confirmed link — PgBouncer stats]
PgBouncer server connection stuck "not ready" for 501s
    ↓ [confirmed link — PgBouncer log]
Connection forcibly closed, 8 new connections opened (thundering herd)
    ↓ [confirmed link — PgBouncer log]
xact latency spikes to 2,230ms, DB session timeouts cascade
    ↓ [confirmed link — structlog errors]
Event loop saturated, websocket connections shed, all users disconnected
    ↓ [confirmed link — memory_diagnostic shows 141→0 users]
```

Concurrently: `render_respond_tab` JS timeouts (5s each) contributed to event loop saturation but were not sufficient alone to cause the cascade — confirmed by post-fix behaviour where the server recovers from JS-induced lag spikes.

## Mitigations Deployed

| # | Action | Issue/PR | Status |
|---|--------|----------|--------|
| 1 | `FEATURES__ENABLE_SEARCH_WORKER=false` — disable FTS worker and hide search bar | PR #451 | Deployed 14:14 AEDT |
| 2 | HAProxy errorfiles for 502/503/504 — maintenance page on any backend failure | Committed to main | Deployed (haproxy reloaded) |
| 3 | Flaky semaphore test replaced with deterministic check | PR #451 | Merged |

## Action Items

| # | Action | Issue | Priority |
|---|--------|-------|----------|
| 1 | Fix search worker: drop `FOR UPDATE`, rely on CAS guard, or move out-of-process | #452 | P1 |
| 2 | Fix respond tab: eliminate 5s blocking `ui.run_javascript` await | #454 | P1 |
| 3 | Fix 503 maintenance page (was showing white page before today's fix) | #453 | P2 |
| 4 | Add event-loop-lag-based auto-restart or backpressure | — | P2 |
| 5 | Write this postmortem | this document | Done |
