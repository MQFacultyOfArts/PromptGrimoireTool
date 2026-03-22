# Post-Mortem: 2026-03-21 PDF Export Failure + Journal PII Leak

*Written: 2026-03-21*
*Investigator: Claude (Opus 4.6)*
*Status: Fix deployed (logging + response_timeout); #403 falsified and closed; #402 open*
*Corrected: 2026-03-22 — pool shrinkage claim falsified, export timeout mechanism corrected*

## Summary

A LAWS5000 student attempted to export a large annotated workspace as PDF.
The export compiled successfully (~85s) but `ui.download()` failed because
the NiceGUI client had been deleted or disconnected during the long compile.
The student retried 4 times. Concurrently, 1,428 annotation page load
timeouts occurred across 68 users in a 15-minute window — caused by the
3.0s `response_timeout` on page loads (now increased to 30s, commit `28eefd31`).

**Correction:** The original summary claimed the export was "killed by response_timeout" and that retries "degraded the connection pool." Both are wrong. The export runs as a click handler (not subject to `response_timeout`). The pool shrinkage hypothesis was falsified (#403). The 1,428 page load timeouts were from the 3.0s `response_timeout` on page load handlers — a pre-existing problem under 68-user load, not caused by the export.

During investigation, a separate critical issue was discovered: the
structlog console handler was dumping student PII (names, document content,
tag data) into systemd journal via `RichTracebackFormatter(show_locals=True)`.

## Timeline (AEDT)

| Time | Event |
|------|-------|
| 19:15 (est.) | Service last restarted Thu 2026-03-19 21:15. Pool overflow at -29 (51 of 80 connections created — normal warm-up, ~~not~~ ~~leakage~~; see #403 falsification). |
| 19:30 | Baseline: 2 annotation timeouts in 4 minutes. Pool: checked_in=49, checked_out=2, overflow=-29/15. |
| 19:34:17 | Export attempt 1 starts. Pandoc converts (28s), TeX generates (27ms). |
| 19:35:43 | LaTeX compiles (57s). `ui.download()` fails: `RuntimeError: The parent element this slot belongs to has been deleted.` Discord webhook fires. |
| 19:35:47 | Export attempt 2 starts. |
| 19:36 | Annotation timeouts spike: 272/min (from baseline 0.5/min). |
| 19:37 | Peak: 520 timeouts/min, 442 INVALIDATE events/min. Export 2 fails same way. |
| 19:39 | Export attempt 3 starts. |
| 19:40 | Export 3 fails. Pool overflow improves from -29 to -22 (new connections created under load). |
| 19:41 | Export attempt 4 starts. |
| 19:43 | Export 4 completes. |
| 19:44 | Cascade subsides. 0 timeouts. |

## Impact

- **User-facing:** 1 student unable to download PDF (4 attempts, all compiled but download failed). PDF files existed on disk in PrivateTmp — manually retrieved and sent to student.
- **Collateral:** 1,428 annotation page timeouts across 68 active users in 15 minutes. Pages that exceed 3s timeout are cancelled AND the client is deleted (NiceGUI behaviour), resulting in broken pages.
- **Pool INVALIDATE churn:** 1,169 INVALIDATE events observed. Pool overflow went from -29 to -22. ~~Originally interpreted as degradation~~ — subsequent investigation (#403) showed `overflow=-29` is normal warm-up accounting (51 of 80 connections created), not capacity loss. The pool self-heals after invalidations.
- **PII leak (discovered during investigation):** Student names, workspace UUIDs, document content, and tag data found in systemd journal via `show_locals=True` traceback dumps. 99 instances of a student name in a 15-minute journal window. Journal was 93.6% unparseable rich formatting garbage (39,638 of 42,335 lines).

## Contributing Factors

### 1. PDF export depends on NiceGUI client surviving 85s

`_run_pdf_export` is a button click handler, dispatched by NiceGUI as an independent `background_tasks.create()` task (see `nicegui/events.py:463`). It is **not** subject to `response_timeout` — that only governs the initial page load handler (`nicegui/page.py:179-186`). The export runs to completion (85s) regardless of page timeout.

However, `ui.download()` at the end requires a live client. If the client is deleted or disconnected during the 85s (user refreshes, navigates away, or NiceGUI prunes the client), `ui.download()` fails with `RuntimeError: The parent element this slot belongs to has been deleted`.

**Evidence grade:** Stack trace at `pdf_export.py:400` is demonstrated. The click-handler dispatch path is code-verified (`nicegui/events.py:463`). The claim that exports are not cancelled by `response_timeout` is inference from this code path — not proven by production log correlation.

**Correction (2026-03-22):** Original text incorrectly stated the export runs "inside a handler context subject to `response_timeout`" and that "NiceGUI cancels the handler." The page load handler and button click handler are separate asyncio tasks. `response_timeout` cancels the page load handler only.

### 2. NiceGUI response_timeout is 3.0s (default, never overridden)

`page_route` in `pages/registry.py:175` does not pass `response_timeout` to `ui.page()`. This was identified as a problem in the #377 investigation (Finding 6, 2026-03-18) with a recommended stopgap (increase to 10s). The stopgap was never applied.

**Evidence grade:** Demonstrated. Code verified at `registry.py:175`.

### 3. ~~CancelledError permanently shrinks connection pool~~ FALSIFIED

**This claim is false.** Subsequent investigation (#403) demonstrated that:

- `QueuePool.overflow()` is a connection-creation counter, not a capacity proxy. `overflow=-29` with `pool_size=80` means 51 connections were created (normal warm-up under ~50 concurrent students), not "29 slots lost."
- Active-query cancellation triggers INVALIDATE events, but the pool recreates connections on next checkout. Full `pool_size` capacity is preserved after repeated cancellations.
- A control test (normal session lifecycle, no cancellation) produces identical overflow shifts.

The baseline pool state (`checked_in=49, checked_out=2, overflow=-29`) was consistent with normal operation, not degradation.

**Evidence grade:** Falsified by 5 discriminating tests in `tests/integration/test_pool_cancellation.py`. See `docs/investigations/2026-03-21-pool-shrinkage-403.md`.

**Correction (2026-03-22):** Original text described this as "Plausible." It is now falsified. The sqlalchemy#6652 and #8145 issues describe a different failure mode (connections not returned) that does not reproduce in our scenario — SQLAlchemy's `asyncio.shield` in `AsyncSession.__aexit__` handles the return correctly.

### 4. No user feedback on export progress

The student received no indication that the export was running or had failed. The only signal was "nothing happened" — so they retried 4 times, each retry amplifying the cascade.

### 5. Console log handler leaks PII via show_locals

`structlog.dev.ConsoleRenderer` defaults to `RichTracebackFormatter(show_locals=True)`. Under systemd (no TTY), this dumps ANSI-coloured rich box-drawing tracebacks with full local variable contents into journald. For exception handlers in annotation page code, locals include student names, document IDs, tag data, and workspace content.

**Evidence grade:** Demonstrated. Journal entries contain student names (99 occurrences in 15-minute window). `ConsoleRenderer` defaults verified via `help(structlog.dev.ConsoleRenderer.__init__)`. No TTY guard in logging setup verified at `__init__.py:224`.

## Actions

| # | Action | Status | Ref |
|---|--------|--------|-----|
| 1 | Retrieve student's compiled PDFs from PrivateTmp | Done | — |
| 2 | Fix console handler: TTY guard + JSONRenderer for systemd + show_locals=False | Done (PR pending) | This branch |
| 3 | Guard tests: AST scan for show_locals, isatty guard, functional PII test | Done (PR pending) | This branch |
| 4 | File issue: decouple PDF export from NiceGUI client lifecycle | Done | #402 |
| 5 | File issue: connection pool shrink under CancelledError | Done → **Falsified and closed** | #403 |
| 6 | Increase response_timeout (3s→30s) | **Done** (commit `28eefd31`) | #403 |
| 7 | Implement export compile queue with concurrency limit | Pending | #402 |
| 8 | ~~Add pool health monitoring/alerting~~ | Dropped — pool shrinkage falsified | #403 |

## Relation to Prior Incidents

This is the second PDF-export-triggered cascade. The 2026-03-15 OOM (see `2026-03-15-production-oom.md`) was caused by orphaned lualatex processes consuming all RAM. This incident has a different mechanism (client lifecycle, not process leaks) but the same pattern: long-running LaTeX compilation interacts badly with the web framework's timeout assumptions, and student retries amplify the damage.

The connection pool leak (#403) was first hypothesised in the #377 page load latency investigation (2026-03-18) but was subsequently **falsified** — see #403 investigation. The pool does not permanently shrink under CancelledError.

## Lessons

1. **Identified risks that aren't mitigated are risks that will materialise.** The 3.0s response_timeout was identified as a problem on 2026-03-18. The stopgap (increase to 10s) was documented as "Safe Action #4" but never applied. Three days later it caused a user-facing incident.

2. **Default library settings are not production settings.** `show_locals=True` is a reasonable default for development. In a web application handling student data under systemd, it's a PII leak. Library defaults must be audited for production context.

3. **Incident tooling revealed the PII issue.** Without the `collect-telemetry.sh` pipeline and `incident_db.py` analysis tooling, the journal contamination would not have been discovered. The investment in incident analysis tooling (#377) paid off immediately.
