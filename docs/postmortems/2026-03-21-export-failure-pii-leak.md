# Post-Mortem: 2026-03-21 PDF Export Failure + Journal PII Leak

*Written: 2026-03-21*
*Investigator: Claude (Opus 4.6)*
*Status: Fix deployed (logging); issues filed (export, pool)*

## Summary

A LAWS5000 student attempted to export a large annotated workspace as PDF.
The export compiled successfully (~85s) but the download never reached the
browser because NiceGUI's 3.0s response timeout had already killed the
client. The student retried 4 times, each retry triggering a cascade of
CancelledError events that degraded the connection pool and caused 1,428
annotation page timeouts across all users in a 15-minute window.

During investigation, a separate critical issue was discovered: the
structlog console handler was dumping student PII (names, document content,
tag data) into systemd journal via `RichTracebackFormatter(show_locals=True)`.

## Timeline (AEDT)

| Time | Event |
|------|-------|
| 19:15 (est.) | Service last restarted Thu 2026-03-19 21:15. Pool overflow already at -29 (29 connections leaked over 46 hours). |
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
- **Pool degradation:** 1,169 INVALIDATE events. Pool overflow went from -29 to -22 (net improvement as new connections were created, but absolute state was already degraded).
- **PII leak (discovered during investigation):** Student names, workspace UUIDs, document content, and tag data found in systemd journal via `show_locals=True` traceback dumps. 99 instances of a student name in a 15-minute journal window. Journal was 93.6% unparseable rich formatting garbage (39,638 of 42,335 lines).

## Contributing Factors

### 1. PDF export runs inside NiceGUI client lifecycle

`_run_pdf_export` executes pandoc + LaTeX compilation inside a handler context subject to `response_timeout`. After 3s, NiceGUI cancels the handler and deletes the client. The export continues in background and succeeds, but `ui.download()` at the end fails because the client is gone.

**Evidence grade:** Demonstrated. Stack trace directly shows `RuntimeError: The parent element this slot belongs to has been deleted` at `pdf_export.py:400`. Export timing (85s) far exceeds 3s timeout.

### 2. NiceGUI response_timeout is 3.0s (default, never overridden)

`page_route` in `pages/registry.py:175` does not pass `response_timeout` to `ui.page()`. This was identified as a problem in the #377 investigation (Finding 6, 2026-03-18) with a recommended stopgap (increase to 10s). The stopgap was never applied.

**Evidence grade:** Demonstrated. Code verified at `registry.py:175`.

### 3. CancelledError permanently shrinks connection pool

Each timeout triggers CancelledError on in-flight DB sessions. SQLAlchemy's greenlet bridge does not fully propagate BaseException during pool return (sqlalchemy#6652, #8145). The pool's overflow counter goes negative and never recovers. At baseline (before any exports), 29 of 80 pool connections had been permanently lost over 46 hours of uptime.

**Evidence grade:** Plausible. Pool state measurements are demonstrated (overflow=-29 at baseline, 51 of 80 connections alive). The CancelledError mechanism is documented in SQLAlchemy issues but the causal link between individual timeouts and pool shrinkage has not been directly measured with per-event pool snapshots. To upgrade: instrument `get_session()` to log pool state on CancelledError specifically.

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
| 5 | File issue: connection pool shrink under CancelledError | Done | #403 |
| 6 | Increase response_timeout as immediate stopgap | Pending | #403 |
| 7 | Implement export compile queue with concurrency limit | Pending | #402 |
| 8 | Add pool health monitoring/alerting | Pending | #403 |

## Relation to Prior Incidents

This is the second PDF-export-triggered cascade. The 2026-03-15 OOM (see `2026-03-15-production-oom.md`) was caused by orphaned lualatex processes consuming all RAM. This incident has a different mechanism (client lifecycle, not process leaks) but the same pattern: long-running LaTeX compilation interacts badly with the web framework's timeout assumptions, and student retries amplify the damage.

The connection pool leak (#403) was first hypothesised in the #377 page load latency investigation (2026-03-18) but had not been confirmed with production data until this incident.

## Lessons

1. **Identified risks that aren't mitigated are risks that will materialise.** The 3.0s response_timeout was identified as a problem on 2026-03-18. The stopgap (increase to 10s) was documented as "Safe Action #4" but never applied. Three days later it caused a user-facing incident.

2. **Default library settings are not production settings.** `show_locals=True` is a reasonable default for development. In a web application handling student data under systemd, it's a PII leak. Library defaults must be audited for production context.

3. **Incident tooling revealed the PII issue.** Without the `collect-telemetry.sh` pipeline and `incident_db.py` analysis tooling, the journal contamination would not have been discovered. The investment in incident analysis tooling (#377) paid off immediately.
