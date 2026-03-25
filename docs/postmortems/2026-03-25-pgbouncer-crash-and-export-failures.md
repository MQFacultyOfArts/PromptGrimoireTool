# Incident: PgBouncer Double-Pooling SIGABRT and LaTeX Export Failures

**Date:** 2026-03-25
**Duration:** 11:38–12:12 AEDT (service down 11:50–11:51, degraded 11:38–12:12)
**Severity:** Service down (SIGABRT crash) + degraded (export failures)
**Detection:** UptimeRobot alert at 12:05 AEDT; Discord webhook alerts for LaTeX errors at 12:53, 14:32–14:33 AEDT

## Source Inventory

Two telemetry tarballs were collected. The first (`-1438`, 00:00–14:36 AEDT) included all sources. The second (`-1548`, 00:00–15:48 AEDT) had wider coverage but omitted PgBouncer logs. Both were ingested into a single SQLite database with SHA256 dedup. Counts below are the union.

| Source | Format | Events | Tarball | Window | Timezone |
|--------|--------|--------|---------|--------|----------|
| haproxy.log | haproxy | 119,554 | -1548 | Full day | AEDT (server local) |
| journal.json | journal | 4,537,004 | -1548 | 00:00–15:48 AEDT | AEDT (server local) |
| pgbouncer.log | pgbouncer | 6,577 | -1438 | 00:00–14:36 AEDT | AEDT (server local) |
| postgresql.json | pglog | 370 | -1438 | 00:00–14:36 AEDT | UTC |
| structlog.jsonl | jsonl | 102,675 | -1548 | 00:00–15:48 AEDT | UTC |
| beszel-api | beszel | 940 | both | Full day | UTC |

Collection: `collect-telemetry.sh`, ingested via `incident_db.py`. DB at `output/incident/incident.db`.

## Timeline

All times AEDT (UTC+11). UTC in parentheses where relevant.

| Time (AEDT) | Source | Event |
|---|---|---|
| **00:00** | — | PgBouncer deployed previous day (2026-03-24) with `default_pool_size=80`, app `pool_size=80` |
| **11:38** | HAProxy, JSONL | 504 timeouts begin, 10–25/min. INVALIDATE/CancelledError events already show `overflow=-17/15` — pool accounting already broken at first captured event. [HAProxy, filtered; JSONL, `ts_utc >= '2026-03-25T00:38'`] |
| **11:45** | JSONL/journal | "annotation not ready after 60s" warnings every 200ms; pool fully exhausted (checked_out=79–81, checked_in=0–1); massive INVALIDATE/CancelledError churn [JSONL, filtered] |
| **11:50:58** | journal | `Main process exited, code=exited, status=134/n/a` (SIGABRT). 3.8G process memory peak (systemd cgroup accounting), 4h 13m CPU consumed. 5 leaked semaphore objects in resource tracker. PID 2466779. [journal, priority 5] |
| **11:50:58** | journal | `Failed with result 'exit-code'` [journal, priority 4] |
| **11:51** | HAProxy | 276 × 503 NOSRV (backend unavailable), 32 × 502 [HAProxy, filtered] |
| **11:51:03** | journal | `Scheduled restart job, restart counter is at 1` [journal] |
| **11:51:10** | journal | New process started, PID 3562290, commit `deb8544e` [journal] |
| **11:55–12:02** | HAProxy | Recovery gap — status 0 (connection drops), service starting [HAProxy, filtered] |
| **12:02–12:12** | HAProxy | Second 504 cascade: 700+ `-1` connection errors + 504s as clients reconnect [HAProxy, filtered] |
| **12:05** | UptimeRobot | Alert fired (external detection) |
| **~12:12** | HAProxy | Traffic stabilises [HAProxy, filtered] |
| **12:53** | JSONL/Discord | `latex_subprocess_output` — workspace `b8ea8bbe`, "Text line contains an invalid character" (`^^H`, U+0008 BACKSPACE) [JSONL] |
| **14:32–14:33** | JSONL/Discord | 4 more LaTeX failures — same workspace, same error. Student retrying. [JSONL] |
| **~14:38** | — | First telemetry tarball collected |
| **15:01** | JSONL/Discord | 2 LaTeX failures — workspace `1043e40e`, different student, same `^^H` error [journal, live] |
| **~15:04** | — | PR #426 deployed (control char strip) |
| **~15:10** | — | `DATABASE__URL` reverted to direct PG socket (PgBouncer bypassed) |
| **~15:15** | — | SQL UPDATE applied to clean 7 documents containing control chars |
| **~15:48** | — | Second telemetry tarball collected |

## Findings

### Finding 1: PgBouncer double-pooling caused pool exhaustion and SIGABRT

**Hypothesis:** SQLAlchemy's connection pool (`pool_size=80, max_overflow=15`) sitting on top of PgBouncer's connection pool (`default_pool_size=80`) in transaction mode created a configuration where PgBouncer could not multiplex connections, leading to pool exhaustion and process abort under load.

**Evidence:**
- Source: PgBouncer log (`output/incident/incident.db`, `pgbouncer_events` table, 6,577 rows)
- **446 "server not ready"** events, with server connections stuck for up to **3,426 seconds (57 minutes)**
- Command: `sqlite3 output/incident/incident.db "SELECT count(*) FROM pgbouncer_events WHERE message LIKE '%not ready%'"`
- Result: 446
- Max age command: `sqlite3 output/incident/incident.db "SELECT max(CAST(substr(message, instr(message, 'age=') + 4, instr(substr(message, instr(message, 'age=') + 4), 's') - 1) AS INTEGER)) FROM pgbouncer_events WHERE message LIKE '%not ready%'"`
- Result: 3426
- **639 cancel requests**, **1,620 client close requests** — SQLAlchemy giving up on stuck connections [PgBouncer log, full window]
- Command: `sqlite3 output/incident/incident.db "SELECT count(*) FROM pgbouncer_events WHERE message LIKE '%cancel request%'"`
- INVALIDATE warnings show `overflow=-17/15` from the **first captured event** at 00:38 UTC — pool accounting was already broken before the crash cascade began [JSONL, filtered]
- Beszel system memory: 4.62 GB (59.57%) at 00:50 UTC (nearest sample before crash), dropped to 2.39 GB (30.85%) at 01:00 UTC (nearest sample after restart) [Beszel, 10-min resolution]. Note: Beszel reports **system-wide** memory, not process-specific. The journal's `3.8G memory peak` is process-specific (systemd cgroup accounting).
- Exit code 134 = SIGABRT. 5 leaked semaphore objects in resource tracker. [journal, priority 5–6]

**Mechanism:** SQLAlchemy maintains 80 persistent connections to PgBouncer. In transaction mode, PgBouncer should return server connections to its pool after each transaction, but SQLAlchemy's persistent pool holds the client connections open even when idle. With 80 client connections permanently claiming all 80 server connections, PgBouncer has no free server connections for multiplexing. When `pg_advisory_xact_lock()` holds transactions open for CRDT synchronisation, the server connections cannot be recycled. Additional overflow connections (up to 15) hit PgBouncer's reserve pool (10), with the remaining 5 having nowhere to go.

**Falsification attempts:**
- Could this be an OOM kill? No — exit code 137 would indicate SIGKILL from OOM killer. Exit code 134 is SIGABRT. Process memory peak was 3.8G (systemd), below the 6G MemoryMax.
- Could advisory locks be incompatible with transaction mode? No — `pg_advisory_xact_lock()` is transaction-scoped and releases before PgBouncer reassigns the connection. Research confirms compatibility.
- Was PgBouncer < 1.21 causing prepared statement issues? No — server runs PgBouncer 1.22.0 with `max_prepared_statements=200`.
- Could the CancelledError storm alone trigger abort(), independent of double-pooling? Possible — hundreds of CancelledError events per minute for twelve minutes could corrupt asyncio's task queue or trigger the multiprocessing resource tracker's signal handling. However, the CancelledError storm was caused by pool exhaustion (connections being cancelled as they time out), which was caused by double-pooling. This is the same causal chain — the question is which link triggers `abort()`, not whether double-pooling is involved.

**Confidence:** Corroborated. Multiple independent sources (PgBouncer log, JSONL pool events, Beszel memory, journal exit code) agree on the mechanism. The causal link from pool exhaustion to `abort()` specifically is inferred — we know pool exhaustion preceded the crash, but the exact trigger for `abort()` (whether asyncio event loop corruption, resource tracker assertion, or something else) is not captured in logs.

**Scope:** In-window confirmed.

### Finding 2: LaTeX "invalid character" from PDF-sourced backspace characters

**Hypothesis:** PDF documents extracted via pymupdf4llm contain C0 control characters (specifically U+0008 BACKSPACE) embedded by journal typesetting systems in running headers. These pass through the HTML storage → Pandoc → LaTeX pipeline without sanitisation, causing LuaLaTeX compilation failure.

**Evidence:**
- Source: JSONL, filtered to epoch 11 (deb8544e)
- 10 `latex_compilation_failed` events, all with error `"! Text line contains an invalid character."` [JSONL, filtered]
- Command: `sqlite3 output/incident/incident.db "SELECT count(*) FROM jsonl_events WHERE event = 'latex_compilation_failed' AND extra_json LIKE '%invalid character%'"`
- Result: 10
- 5 failures on workspace `b8ea8bbe` (LAWS5000), 5 on workspace `1043e40e` (LAWS8027). The LAWS8027 failures include 2 at 04:01 UTC (15:01 AEDT), both retries by the same student. [JSONL, filtered]
- LaTeX log shows `l.130 302^^H` — page number 302 followed by backspace [journal, live capture at 15:01]
- Source PDF (66.pdf, Adelaide Law Review) contains U+0008 on every page in running headers, embedded by the journal's typesetting system
- Command: `python3 -c "import pymupdf; doc = pymupdf.open('66.pdf'); [print(f'Page {i+1}') for i, p in enumerate(doc) if chr(8) in p.get_text()]"`
- Result: All 11 pages contain backspace
- The `_strip_control_chars()` function in `unicode_latex.py` correctly handles this for annotation metadata, but the Pandoc HTML→LaTeX body path had no equivalent sanitisation [code inspection]

**Falsification attempts:**
- Could the stdin change (#402, commit `256965d1`) have introduced this? No — the backspace character would have passed through the temp file path equally. The bug was latent; students with this specific PDF are just now attempting exports.
- Could Pandoc be stripping these? No — Pandoc passes `\x08` through from HTML input to LaTeX output. Confirmed by test.

**Confidence:** Confirmed. Direct measurement, reproducible with fixture, fix verified by 6 passing tests.

**Scope:** In-window confirmed. 7 affected documents found in production via `SELECT ... WHERE content ~ E'[\\x01-\\x08...]'`.

### Finding 3: Historical LaTeX errors resolved in current deploy

**Hypothesis:** Earlier LaTeX failure classes observed in epochs 1–8 (22 × `\underLine` nesting errors, 3 × undefined tag colour) have been fixed by subsequent deploys and do not affect the current codebase.

**Evidence:**
- `\underLine` errors: 22 failures in epochs 1, 2, 8 (2026-03-17 to 2026-03-22). All from LAWS5056/LAWS8029 "Dog's Breakfast" activity. Workspace `2bfad271` tested live — exports successfully on current deploy. [JSONL, historical epochs; live test]
- Undefined tag colour: 3 failures in epoch 8 (2026-03-22), workspace `2123c585`. Tested live — no error. [JSONL, epoch 8; live test]

**Confidence:** Confirmed. Live export tests on affected workspaces pass on current deploy.

**Scope:** Out-of-window corroboration (historical data contextualises current state).

## Contributing Factors

1. **PgBouncer deployed with matching pool sizes** (2026-03-24) — `default_pool_size=80` matched SQLAlchemy's `pool_size=80`, creating a 1:1 mapping that eliminated multiplexing benefit. **Confirmed link:** PgBouncer log shows 446 "not ready" events with ages up to 57 minutes — server connections permanently claimed.

2. **SQLAlchemy's persistent pool defeats transaction-mode multiplexing** — QueuePool holds connections open even when idle, preventing PgBouncer from recycling server connections between transactions. **Confirmed link:** pool overflow going negative (`-17/15`) from the first INVALIDATE event indicates pool accounting breakdown.

3. **Advisory lock contention under load** — `pg_advisory_xact_lock()` for CRDT synchronisation holds transactions open for 3–10 seconds during peak load, preventing PgBouncer from returning server connections. **Confirmed link:** PG log shows advisory lock durations of 3,450–9,746 ms. Command: `sqlite3 output/incident/incident.db "SELECT substr(message, 1, 100) FROM pg_events WHERE message LIKE '%advisory%' LIMIT 5"`.

4. **196 active users at peak** — Tuesday teaching load saturated the misconfigured pool. The same user count was handled successfully for weeks on direct PG without PgBouncer. **Source:** JSONL user activity query; command: `sqlite3 output/incident/incident.db "SELECT count(DISTINCT user_id) FROM jsonl_events WHERE user_id IS NOT NULL AND ts_utc >= '2026-03-25T00:00' AND ts_utc < '2026-03-25T04:00'"`.

5. **PDF content with embedded control characters** — journal typesetting systems embed C0 control characters in running headers. pymupdf4llm extracts faithfully, Pandoc passes through, no sanitisation on the body path. **Confirmed link:** direct examination of source PDF and pipeline code.

## Peer Review

Reviewed by proleptic-challenger agent (2026-03-25). Key issues addressed in this revision:

- Source inventory updated to reflect both tarballs with correct event counts
- PgBouncer "not ready" count verified reproducible: 446 events, max age 3,426s (corrected from 3,095s)
- Cancel request count corrected: 639 (was 351), client close count corrected: 1,620 (was 415)
- Beszel memory figures corrected to exact values (4.62 GB / 59.57%, 2.39 GB / 30.85%) with note distinguishing system-wide from process-specific memory
- Timeline corrected: overflow was already negative from first event at 11:38, not progressing toward saturation at 11:45
- Timeline chronological order fixed (15:04 deploy moved before 15:10 revert)
- 15:01 AEDT entry corrected to note 2 failures, not 1
- CancelledError storm as alternative SIGABRT trigger added to falsification attempts
- Contributing Factor 3 now cites PG log query with provenance command
- Contributing Factor 4 now includes provenance command for user count

## Action Items

| # | Action | Issue | Priority | Status |
|---|--------|-------|----------|--------|
| 1 | Revert to direct PG connection (bypass PgBouncer) | — | P0 | **Done** (2026-03-25) |
| 2 | Strip C0/C1 control chars from Pandoc output | #426 | P0 | **Done** (PR merged) |
| 3 | SQL cleanup of 7 documents with control chars | — | P0 | **Done** (2026-03-25) |
| 4 | Re-enable PgBouncer with NullPool | #427 | P1 | Open — needs load testing |
| 5 | Input-side control char guard in sanitisation.py | — | P2 | Not filed — follow-up to #426 |
| 6 | Exclude perf tests from standard Playwright lane | #426 (branch) | P2 | **Done** (committed) |
| 7 | Store incident data in `output/incident/`, not `/tmp` | — | P3 | **Done** (skill updated) |
