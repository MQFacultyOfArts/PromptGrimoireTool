# Afternoon Incident Analysis: 2026-03-16 14:50–17:20 AEDT

*Analysis performed 2026-03-16 evening. Revised after internal peer review (proleptic challenger).*

## Methodology

### Data Collection

Logs were collected from the production server (`grimoire.drbbs.org`) via `journalctl`, `cp`, and `scp`. Beszel metrics were read visually from the dashboard (not machine-exported).

### Analysis Commands

All JSONL queries were filtered to the afternoon window using:
```bash
jq 'select(.timestamp >= "2026-03-16T03:50" and .timestamp <= "2026-03-16T06:20")' /tmp/incident-20260316-afternoon.jsonl
```
(AEDT = UTC+11, so 14:50 AEDT = 03:50 UTC)

Journal grep used `rtk proxy grep` to bypass the rtk hook's output transformation. HAProxy status codes were extracted with regex ` NNN ` (space-padded to avoid partial matches). PG log was scanned for `ERROR|FATAL` lines with date prefix filtering.

### Peer Review Corrections

An internal proleptic challenger reviewed the first draft and identified:
1. The JSONL file spans 28 hours (Mar 15 13:57 – Mar 16 17:45 AEDT), not the 2.5-hour afternoon window. All JSONL-derived counts in the original draft were inflated. Corrected below.
2. Finding 3 ("No PostgreSQL-Level Errors") was factually wrong — 10 ERRORs and 3 FATALs occurred during the afternoon. Corrected below.
3. The 5xx total was 106, not 82. Additional status codes (500, 501, 502, 505, 506, 508) were not analysed. Corrected below.
4. INVALIDATE events with `size=5` were from the morning (pre-pool-increase). These contaminated the afternoon analysis. Removed.
5. The "1,967 errors" figure was not reproducible from either the filtered or unfiltered JSONL. Replaced with verified counts.

### Limitations

- **Beszel metrics were read visually**, not exported. CPU/memory/load numbers are approximate.
- **HAProxy logging was only fixed at 12:38 AEDT** (see incident-response.md). No HAProxy data exists before that time.
- **JSONL `exc_info` is null for DB rollback events.** Root cause identification required cross-referencing journal tracebacks.
- **Discord severely undercounted errors.** ~16 Discord alerts for 680 JSONL error events (afternoon-only). Cause unknown (rate limiting, deduplication, or webhook failures).
- **PG log covers Mar 14–16 entire.** Filtered to `2026-03-16 04:*–06:*` UTC for afternoon analysis.
- **HAProxy 137.111.13.x is MQ campus NAT.** Individual student attribution from HAProxy alone is not possible.
- **Login events undercount active users.** Students with persistent sessions from before the restart would not generate login events.
- **Websocket reconnections are not login events.** The "max 2 re-logins per student" claim only covers authentication, not page refreshes or WS reconnects.

## Data Sources

| Source | Path | Coverage | Total lines | Afternoon lines |
|--------|------|----------|------------:|---------:|
| Application journal | `/tmp/incident-20260316-afternoon.log` | 14:50–17:20 AEDT | 502,716 | 502,716 |
| Structured JSONL | `/tmp/incident-20260316-afternoon.jsonl` | Mar 15 13:57 – Mar 16 17:45 AEDT | 10,091 | 6,646 |
| HAProxy access log | `/tmp/haproxy-20260316.log` | 12:38–17:48 AEDT | 19,776 | 19,776 |
| PostgreSQL log | `/tmp/pglog-20260316-afternoon.log` | Mar 14–16 (full file) | 715 | ~30 |
| Beszel metrics | Visual inspection (not machine-captured) | 14:50–17:20 AEDT | N/A | N/A |
| Discord webhook alerts | Manual review | 14:56–17:14 AEDT | ~16 alerts | ~16 |

## Finding 1: Intentional Service Restart at 15:02:29

**Method:** `grep -E "Stopping|Started|Stopped|Deactivated|Consumed"` on journal; PID counts via `grep -c "promptgrimoire\[PID\]"`.

**Evidence:** systemd journal shows clean stop/start cycle:
```
Mar 16 15:02:29 systemd[1]: Stopping promptgrimoire.service
Mar 16 15:02:29 systemd[1]: Deactivated successfully
Mar 16 15:02:29 systemd[1]: Consumed 24min 31.405s CPU time, 2.4G memory peak
Mar 16 15:02:29 systemd[1]: Started promptgrimoire.service
```
PID changed from 885075 (6,452 log lines) to 1168211 (496,264 log lines).

**Impact:** HAProxy returned 54 x 503 (`<NOSRV>`) during the restart window. This was the largest single burst of 5xx errors.

**Confidence:** High. No OOM kill (dmesg clean), clean systemd lifecycle. This was the deploy of #360/#361 fixes.

**Caveat:** We assume this was a manual deploy but have not verified via shell history.

## Finding 2: Connection Pool Churn Under Load

**Method:** JSONL filtered to afternoon, `jq 'select(.event | startswith("INVALIDATE"))'`, grouped by minute from journal via `awk` on timestamps. Pool state read from INVALIDATE event fields.

**Evidence:** INVALIDATE events (afternoon-only, all `exception=CancelledError`, all `size=10`):

| Window (AEDT) | INVALIDATEs/min | Peak checked_out | Peak overflow |
|----------------|----------------:|------------------:|--------------:|
| 15:25–15:32 | ~5–8 | 10 | 3/20 |
| 15:38–15:54 | 70–116 | 30 | 20/20 |
| 16:06–16:13 | 41–122 | 30 | 20/20 |
| 17:03–17:14 | 1–22 | Low | Low |

Pool configuration (post-commit `a85c1226`): `pool_size=10`, `max_overflow=20` (ceiling: 30). Note: the pool was increased from `size=5, max_overflow=10` between the morning and afternoon incidents. The afternoon still hit capacity, suggesting the increase was necessary but insufficient.

**Interpretation:** The pool reached its ceiling (`checked_out=30, overflow=20/20`) during peak load. Zero `QueuePool limit` errors — the pool was at capacity but connections were churning (destroyed by CancelledError, recreated), not exhausted. This correlates with 3 x PG `FATAL: connection to client lost` at 15:50, 15:52, 16:10 (see Finding 3).

**Confidence:** Medium. The pool reaching capacity is confirmed by the INVALIDATE fields. The causal mechanism ("students navigating away") is inferred from CancelledError semantics. CancelledError could also arise from NiceGUI's internal task management, event loop saturation, or other async cancellation sources.

## Finding 3: PostgreSQL Errors During Afternoon (CORRECTED)

**Method:** `grep -E "ERROR|FATAL" pglog | grep "2026-03-16 0[4-6]"` (04:00–06:20 UTC = 15:00–17:20 AEDT).

**Evidence (original draft said "no PG errors" — this was wrong):**

| Time (UTC) | Time (AEDT) | Type | Detail |
|-----------|-------------|------|--------|
| 04:32:52 | 15:32 | ERROR x2 | `uq_tag_workspace_name` violation |
| 04:50:16 | 15:50 | FATAL | connection to client lost |
| 04:52:54 | 15:52 | FATAL | connection to client lost |
| 05:10:24 | 16:10 | FATAL | connection to client lost |
| 05:11:18–45 | 16:11 | ERROR x8 | `uq_tag_workspace_name` violation |

The 3 x `FATAL: connection to client lost` correlate with the INVALIDATE churn peaks in Finding 2 (15:50 and 16:10 are during the two main surge windows). These confirm that PG-side connection drops were occurring — the application's CancelledError destruction of connections was visible to PostgreSQL as abrupt client disconnections.

The 10 x `uq_tag_workspace_name` violations are tag duplicate constraint violations, matching Finding 7.

**Confidence:** High. Direct PG log evidence. The original draft missed these due to incorrect date filtering (the analyst forgot the UTC offset when scanning).

**What remains true:** PG memory was stable (262.7 MB peak per Beszel), PG was not the bottleneck, and no PG-side resource exhaustion occurred.

## Finding 4: Upload Stall at 16:06 (504 Gateway Timeouts)

**Method:** `grep " 504 " haproxy.log`, response time extracted from HAProxy log format field.

**Evidence:** HAProxy logged 15 x 504 responses, 14 concentrated at 16:06, all on `/upload` endpoints:
```
16:06:14 POST /_nicegui/client/.../upload/71 ... 504 ... 61014ms
16:06:15 POST /_nicegui/client/.../upload/71 ... 504 ... 60799ms
```
The ~61s response time indicates HAProxy's 60-second timeout was hit.

**Correlation:** Colleague reported ~50 students uploading PDFs simultaneously in 4pm class, experiencing "stalled for a couple of minutes" then self-correction. The 14 x 504 tells us 14 uploads exceeded the timeout. We do not know how many succeeded — the 50-student figure is anecdotal, not derived from logs.

**Confidence:** High for the symptom. Medium for root cause — event loop saturation, DB pool at capacity, or both.

## Finding 5: Application Error Breakdown (CORRECTED — afternoon-only)

**Method:** `jq -r 'select(.timestamp >= "2026-03-16T03:50" and .timestamp <= "2026-03-16T06:20") | [.level, .event] | @tsv'`, piped to `sort | uniq -c | sort -rn`.

**Totals (afternoon-only):** 6,646 log entries. By level: 3,303 warning, 1,973 debug, 690 info, 680 error.

| Category | Count | Level | Events |
|----------|------:|-------|--------|
| Page load latency | 1,725 | warning | "not ready after 3.0s" (1,689 annotation, 36 navigator) |
| Connection churn | 1,352+ | warning | INVALIDATE CancelledError (various pool states, all `size=10`) |
| NiceGUI rebuild overhead | 143 | warning | Event listeners re-rendered |
| JS timeout (1s) | 212 | error | JavaScript did not respond within 1.0 s |
| Stytch SDK leak | 229 | error | Unclosed client session (160), unclosed connector (69) |
| NiceGUI UI races | 63 | error | Slot deleted (58), list.index (5) |
| Async task leak | 51 | error | Task exception never retrieved |
| LaTeX/export failure | 34 | error | latex_subprocess_output (17), compilation failed (17) |
| Failed PDF export | 17 | error | Failed to export PDF |
| DB session rollback | 19 | error | See Finding 6 |
| ASGI exception | 21 | error | Exception in ASGI application |
| JS timeout (5s) | 8 | error | JavaScript did not respond within 5.0 s |
| Input sanitisation | 6 | error | Script tag in HTML elements |
| Invalid select value | 4 | error | ui.select stale UUID |

**Note:** Tag duplicate warnings (43 `duplicate_tag_name`) are not in this table because they fall outside the afternoon JSONL window or were logged to journal only. See Finding 7 for tag analysis.

**Reconciliation with journal:** The journal `grep -c "\[error"` found 786 lines. This counts the `[error` prefix line of multi-line tracebacks; JSONL collapses each traceback to one entry (680 afternoon errors). The ~100-line discrepancy may be from rich traceback formatting that includes `[error` in frame content, not as log-level prefixes. We did not fully reconcile these counts.

## Finding 6: DB Rollback Errors (CORRECTED — 19 afternoon-only, not 91)

**Method:** JSONL filtered to afternoon for count (19). Journal `grep -A 30 "Database session error"` for traceback identification. `grep -E "PermissionError|TimeoutError|asyncpg"` within traceback windows.

**Evidence (afternoon-only, 19 events):**

The "Database session error, rolling back transaction" message is a **generic catch-all** from `db/engine.py:299` (`except Exception`). It wraps at least three distinct root causes:

| Root cause | Afternoon count | How identified |
|-----------|:-:|---|
| `PermissionError: sharing is not allowed` | Unknown (see below) | Journal traceback at `acl.py:456` |
| `PermissionError: cannot modify owner permission` | Unknown (see below) | Journal traceback at `acl.py:475` |
| `asyncpg TimeoutError` | 3 | Journal traceback at asyncpg `connect_utils` |

**Caveat:** We identified the PermissionError pattern from journal `grep -B 2` which returned 36 hits across the full journal file (not afternoon-filtered). The journal timestamps for these cluster at 17:03–17:04 and 17:12–17:14, which IS within the afternoon window, but we did not rigorously verify all 36 fall within the window. The 19 JSONL events and 36 journal grep hits have not been reconciled.

**Root cause for share errors (investigated post-draft):** Code review of `db/acl.py` and `pages/annotation/sharing.py` revealed two bugs:
1. **`sharing.py:68`** — The "Share with user" button checks `can_manage_sharing` but ignores `allow_sharing`. Students see a share button even when sharing is disabled for the activity.
2. **Loose workspaces default `allow_sharing=False`** — Workspaces not attached to an activity inherit `False`, but loose workspaces should allow sharing.

These bugs mean students click a visible share button, the backend rejects it, and the generic exception handler logs it as a "DB error." It is a **UI bug causing false DB error alerts**, not a database issue.

**Confidence:** High for the share bug (confirmed via code review). Medium for the quantitative breakdown (counts not fully reconciled between JSONL and journal).

## Finding 7: Tag Duplicate Errors

**Method:** JSONL `duplicate_tag_name` warning count; PG log `uq_tag_workspace_name` errors.

**Evidence:**
- PG log: 10 x `uq_tag_workspace_name` violations during afternoon (2 at 15:32, 8 at 16:11)
- JSONL: 43 `duplicate_tag_name` warnings (from unfiltered JSONL — these may span both morning and afternoon; afternoon-only count not separately verified)

**Interpretation:** The #360/#361 deploy added `DuplicateNameError` handling. The JSONL warnings suggest the new code path IS catching duplicates gracefully. The PG errors may be from the brief window before the deploy took effect (PID 885075, pre-restart), or from race conditions where two concurrent tag creations hit the constraint despite the application-level check.

**Confidence:** Low-medium. We have not separated pre-restart (PID 885075) from post-restart (PID 1168211) tag errors to determine whether the fix reduced the PG-level violations. The new-errors doc (item #2) reports a tag organise regression (colour/name changes not propagating), which is a separate issue from duplicate handling.

## Finding 8: Student Load Profile

**Method:** `grep "Login successful" | sed 's/.*email=//' | sort -u | wc -l` for unique students. `awk` timestamp extraction for surge timing. `grep "INVALIDATE" | sed 's/.*user_id=//' | sort -u | wc -l` for affected users.

**Evidence:**
- 169 unique students logged in (authentication events only)
- Three class arrival surges: 15:06 (19 logins post-restart), 16:02–16:03 (38 logins), 17:07–17:09 (25 logins)
- Maximum re-login count per student: 2 (authentication events only — does NOT count page refreshes or WS reconnects)
- 125 unique users (74%) triggered at least one INVALIDATE event

**Beszel metrics (visual, approximate):**
- CPU: peaked ~48% at ~15:10, local maximum ~38% at ~16:10, baseline ~15%
- Memory: grimoire peaked ~3.11 GB, postgres peaked ~262.7 MB
- Load: ~0.59 at 15:30, ~1.07 at 15:40, ~1.00 at 16:20
- Disk: stable

**Confidence:** High for login counts. Low for Beszel (visual estimates, not machine-exported).

## Finding 9: HAProxy 5xx Breakdown (NEW)

**Method:** `for code in 500 501 502 503 504 505 506 508; do grep -c " $code " haproxy.log; done`. Timeline via timestamp extraction and `sort | uniq -c`.

**Evidence:**

| Code | Count | Meaning |
|------|------:|---------|
| 200 | 10,090 | OK |
| 101 | 8,421 | WebSocket upgrades |
| 304 | 601 | Not modified |
| 400 | 287 | Bad request |
| 500 | 15 | Internal server error |
| 501 | 5 | Not implemented |
| 502 | 12 | Bad gateway |
| 503 | 54 | Backend unavailable |
| 504 | 15 | Gateway timeout |
| 505 | 2 | HTTP version not supported |
| 506 | 2 | Variant also negotiates |
| 508 | 1 | Loop detected |
| 404 | 38 | Not found |
| **5xx total** | **106** | |

5xx timeline:
- **15:02** — 54 x 503 (restart, `<NOSRV>`)
- **16:06** — 14 x 504 (upload stall)
- **Remaining 38** — scattered 500/501/502/505/506/508, not individually investigated

**Open questions:** The 15 x 500 (Internal Server Error) and 12 x 502 (Bad Gateway) are unanalysed. 502s from HAProxy typically indicate the backend closed the connection mid-request — these may correlate with the PG `FATAL: connection to client lost` events. The 287 x 400 (Bad Request) also unanalysed.

**Confidence:** High for counts. Low for interpretation of non-503/504 codes (not investigated).

## Finding 10: Empty Student ID Unique Constraint Issue

**Method:** PG log `grep "uq_user_student_id"`.

**Evidence:** PG log shows 5+ violations from **Mar 15** (morning incident, not afternoon) where `Key (student_id)=() already exists` — empty string, not NULL.

**Interpretation:** The `student_id` column has a unique constraint, and multiple users have `student_id = ''`. Empty strings should be NULL (which allows multiple rows) or excluded from the unique constraint.

**Confidence:** High for the symptom. Not verified whether this has been addressed. These were NOT afternoon errors — they are included here for completeness as they appeared in the same PG log file.

## Finding 11: Share Button Visible When Sharing Disabled (NEW — found during live investigation)

**Method:** Code review of `pages/annotation/sharing.py` and `db/acl.py`, triggered by DB rollback errors continuing to fire at 19:38–19:39 AEDT (post-analysis-window, same PID 1168211).

**Evidence:** Two distinct bugs confirmed:

1. **`sharing.py:68`** — The "Share with user" button guards on `can_manage_sharing` but not `allow_sharing`. Compare with line 48 where "Share with class" correctly guards on both. Students see a share button, open the dialog, enter an email, submit, and the backend rejects it at `acl.py:456` (`sharing is not allowed for this workspace`).

2. **`workspaces.py:158`** — `WorkspaceContext.allow_sharing` defaults to `False`. Loose workspaces (not attached to an activity/course) inherit this default. But loose workspaces should allow sharing since there is no course policy to enforce.

The DB session context manager (`engine.py:299`) catches the PermissionError via the generic `except Exception`, logs it as "Database session error, rolling back transaction", and triggers a Discord alert. This inflates DB error counts and masks the actual issue (UI bug).

**Confidence:** High. Confirmed via code review and live log reproduction.

## Summary: What Hurt Students

1. **Restart at 15:02** — 54 x 503, ~10 seconds of complete unavailability
2. **Upload stall at 16:06** — 14 x 504 timeouts, ~2 minutes of degraded upload
3. **Page load latency** — 1,725 "not ready after 3s" warnings, consistent throughout afternoon
4. **JS timeouts** — 220 events (212 x 1s, 8 x 5s), UI unresponsiveness under load

## What Did NOT Happen

- No OOM kill (dmesg clean, memory stable)
- No QueuePool exhaustion errors (pool reached capacity but did not refuse connections)
- No data loss evidence (no CRDT/DB divergence logged)
- No sustained outage (all issues self-resolved)

## Open Questions

1. What are the 15 x 500 and 12 x 502 HAProxy errors? Do 502s correlate with PG FATAL events?
2. What are the 287 x 400 (Bad Request) responses in HAProxy?
3. Are the 11 `tag_creation_failed` errors a regression from #360/#361?
4. What caused the 6 bulk enrolment failures?
5. Does the CancelledError churn have a mitigation (e.g., `pre_ping`, NiceGUI task cancellation handling)?
6. Is the PG log complete, or did log rotation truncate it? Last entry is 06:44 UTC.

## Bugs Found During Analysis

| Bug | Location | Impact | Recommended fix |
|-----|----------|--------|-----------------|
| Share button shown when sharing disabled | `sharing.py:68` | False DB error alerts, confusing UX | Guard on `allow_sharing` like line 48 |
| Loose workspaces default sharing off | `workspaces.py:158` | Students can't share loose workspaces | Default `allow_sharing=True` for loose |
| PermissionError logged as DB error | `engine.py:299` | Inflated DB error counts, false alerts | Catch before `get_session()` or log as warning |
| Discord alert lacks exception type | `logging_discord.py` | "DB error" alert with no root cause | Include exception class in alert embed |
| Empty student_id unique constraint | Schema | Enrolment failures for users without student ID | Use partial unique index excluding empty strings |

## Recommendations (Pending Review)

1. **Fix share button visibility** — hide when `allow_sharing=False` (bug, not feature request)
2. **Fix loose workspace sharing default** — `allow_sharing=True` for workspaces without activity context
3. **Reclassify PermissionError** — catch before DB session or log as warning, not error
4. **Include exception type in Discord alerts** — "DB rollback: PermissionError" not just "DB error"
5. **Load test concurrent uploads** — benchmark with 50+ concurrent PDF uploads (anecdotal class size, not verified)
6. **Investigate CancelledError pool churn** — dominant load pattern, correlates with PG connection drops
7. **Analyse remaining 5xx codes** — 500, 502, and 400 responses are uncharacterised
