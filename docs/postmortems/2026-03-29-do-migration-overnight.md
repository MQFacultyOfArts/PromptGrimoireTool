# Migration Review: NCI to DigitalOcean (overnight 2026-03-28/29)

**Date:** 2026-03-28 to 2026-03-29
**Duration:** Migration window 19:00–00:15 AEDT; monitoring window 00:00–09:00 AEDT
**Severity:** Non-incident (false alarm)
**Detection:** UptimeRobot alerts (4 down/up cycles overnight)

## Summary

PromptGrimoire migrated from NCI Cloud (130.56.245.37) to DigitalOcean SYD1 (170.64.140.42) on the evening of 2026-03-28. UptimeRobot reported 4 "down" events overnight. Investigation confirmed these were DNS propagation artefacts — the application never restarted after the initial deploy.

## Source Inventory

| Source | Format | Events | Window (UTC) |
|--------|--------|--------|-------------|
| haproxy.log | haproxy | 7,320 | 2026-03-28 11:00–22:00 |
| journal.json | journal | 6,846 | 2026-03-28 11:00–22:00 |
| structlog.jsonl | jsonl | 145,549 | 2026-03-28 11:00–22:00 |
| postgresql.log | pglog | 75 | 2026-03-28 11:00–22:00 |
| pgbouncer.log | pgbouncer | 49,784 | 2026-03-28 11:00–22:00 |

## Timeline (AEDT = UTC+11)

| Time (AEDT) | Event | Source |
|-------------|-------|--------|
| 23:56 Mar 28 | Deploy restart — commit 8b1b438e (#448) | journal |
| 00:08 Mar 29 | Final restart (PID 396186) — ran continuously for 9h | journal |
| 00:14 | UptimeRobot: first "up" detection | UptimeRobot |
| 00:35 | UptimeRobot: "down" | DNS propagation |
| 00:45 | UptimeRobot: "up" | DNS propagation |
| 01:02 | UptimeRobot: "down" | DNS propagation |
| 01:07 | UptimeRobot: "up" | DNS propagation |
| 03:25 | UptimeRobot: "down" | DNS propagation |
| 03:30 | UptimeRobot: "up" | DNS propagation |
| 07:06 | UptimeRobot: "down" | DNS propagation |
| 07:11 | UptimeRobot: "up" (stable) | DNS propagation |

## Findings

### Finding 1: Application did not restart overnight

**Hypothesis:** The 4 UptimeRobot "down" events correspond to application crashes or restarts.

**Evidence:**
- PID 396186 ran continuously from 13:08:05 UTC to 21:59:59 UTC (99,944 JSONL events) [JSONL, full window]
- PID 396206 (export worker) ran continuously from 13:08:07 UTC to 21:59:57 UTC (32,308 events) [JSONL, full window]
- Journal shows only two restarts: deploy at 12:56 UTC and final startup at 13:08 UTC [journal, full window]
- No further `Stopping`/`Started`/`Consumed` journal entries after 13:08 UTC

**Falsification:** Checked for PID changes in JSONL — only two PIDs active after 13:08 UTC, both ran to end of window. No OOM kills in journal.

**Confidence:** Confirmed — direct measurement from two independent sources (JSONL PIDs, journal lifecycle messages).

### Finding 2: UptimeRobot "downs" caused by DNS propagation

**Hypothesis:** UptimeRobot intermittently resolved the old NCI IP (130.56.245.37, server stopped) instead of the new DO IP during DNS propagation.

**Evidence:**
- HAProxy on DO served normal 200/101/304 responses at every reported "down" time [HAProxy, full window]:
  - 13:35 UTC (00:35 AEDT): 200s, 101s, 400s — normal traffic
  - 14:02 UTC (01:02 AEDT): 200s, 101s, 304s — normal traffic
  - 16:25 UTC (03:25 AEDT): 200s, 101s — normal traffic
  - 20:06 UTC (07:06 AEDT): 200s, 101s, 304s — normal traffic
- Zero 503s at any of the reported "down" times
- WATCHDOG event loop checks showed 0.000s response times throughout [JSONL, PID 396186]

**Falsification:** If the app were actually down, HAProxy would show 503 NOSRV responses. None observed at the reported times.

**Confidence:** Corroborated — HAProxy shows the app was responding, but we cannot directly observe UptimeRobot's DNS resolution path. The DNS propagation explanation is the simplest fit for intermittent external-only unreachability with continuous local availability.

### Finding 3: Export worker operating correctly on standalone mode

**Evidence:**
- Worker PID 396206 processing exports at ~4s per workspace [JSONL, PID 396206]
- `export_worker_skipped` logged by app (PID 396186) confirming `FEATURES__WORKER_IN_PROCESS=false` mode active
- One `export_pdf_missing` at 13:05 UTC — pre-restart PID 381235 couldn't find PDF written by PID 384512 (different process, likely PrivateTmp namespace mismatch before the workaround stabilised)

**Confidence:** Confirmed.

### Finding 4: Vulnerability scanning on new IP

**Evidence:**
- Epoch 6 shows ~400 "not found" warnings for paths like `/.env`, `/.git/config`, `/.aws/credentials`, `/etc/passwd` traversals, nmap fingerprinting [JSONL, epoch 6]
- All from external IPs probing the newly-public DO droplet
- No successful exploits — all returned 404

**Confidence:** Confirmed — normal internet background noise on a fresh public IP.

### Observation: Export xcolor failures (separate bug)

Three workspaces fail PDF export with `xcolor Error: Undefined color 'tag-<UUID>-dark'`. These are tags whose colour definitions are not being emitted in the LaTeX preamble — likely orphaned tag references or tags created without colour values. Not related to the migration.

## Contributing Factors

1. **DNS-only cutover** — no proxy bridge from old to new IP during propagation
2. **NCI server stopped but not decommissioned** — old IP unreachable, causing timeouts for clients resolving the old address
3. **UptimeRobot may not have been updated to use the new IP directly** — relying on DNS instead

## Action Items

| # | Action | Priority |
|---|--------|----------|
| 1 | For future migrations: configure old HAProxy as reverse proxy to new server before DNS cutover | P2 |
| 2 | Update UptimeRobot to monitor DO IP directly (not DNS-dependent) | P1 |
| 3 | Fix xcolor export bug — define fallback colour for undefined tag UUIDs | P2 |
| 4 | Decommission NCI server (currently stopped, not terminated) | P3 |
