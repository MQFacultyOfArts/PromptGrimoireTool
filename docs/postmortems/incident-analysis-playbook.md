# PromptGrimoire Incident Analysis Playbook

*Standing playbook for production incident investigation. Applies the methodology from the `incident-analysis` skill to PromptGrimoire's specific infrastructure.*

*Last updated: 2026-03-24. Created from lessons learned during the 2026-03-16 morning and afternoon incidents. Updated with automated tooling (`collect-telemetry.sh`, `incident_db.py`), corrected pool configuration, JS timeout epoch analysis, and dataset building workflow.*

## Log Sources

### Source Inventory Template

Copy this table into every incident analysis report and fill it in **before any analysis begins**. This is the provenance manifest.

| Source | Server path | Timezone | Collection command |
|--------|------------|----------|-------------------|
| Application journal | systemd journal for `promptgrimoire.service` | Server local (`Australia/Sydney`) | `sudo journalctl -u promptgrimoire --no-pager -S "HH:MM" -U "HH:MM" > /tmp/incident-YYYYMMDD.log` |
| Structured JSONL | `/opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl` | UTC (ISO 8601) | `sudo cp /opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl /tmp/incident-YYYYMMDD.jsonl` |
| HAProxy access log | `/var/log/haproxy.log` | Server local (`Australia/Sydney`) | `sudo cp /var/log/haproxy.log /tmp/haproxy-YYYYMMDD.log && sudo chmod 644 /tmp/haproxy-YYYYMMDD.log` |
| PostgreSQL log | `/var/log/postgresql/postgresql-16-main.log` | **UTC** (configured in `postgresql.conf`) | `sudo cp /var/log/postgresql/postgresql-16-main.log /tmp/pglog-YYYYMMDD.log && sudo chmod 644 /tmp/pglog-YYYYMMDD.log` |
| Beszel metrics | Dashboard via SSH tunnel (`ssh -L 8090:localhost:8090 brian.fedarch.org`) | Browser local | Visual inspection only — not machine-exportable |
| Discord webhook alerts | Discord channel | Server local | Manual review — severely undercounts (expect 10–50x fewer alerts than actual errors) |

### Timezone Conversion

The server runs `Australia/Sydney`. This is AEDT (UTC+11) during daylight saving (first Sunday in October to first Sunday in April) and AEST (UTC+10) otherwise.

**Critical:** PG logs are UTC. To find events at 15:00 AEDT, search for `04:00 UTC` (AEDT-11). To find events at 15:00 AEST, search for `05:00 UTC` (AEST-10).

**Positive control:** After setting up any time filter, verify it works by searching for a known event (e.g., a service restart). If a filter returns zero results, verify the filter before reporting zero. On 2026-03-16, a PG log search for afternoon errors returned zero because the analyst used local-time prefixes against UTC timestamps. 13 errors were missed.

### Collection Procedure (Automated)

The `collect-telemetry.sh` script automates collection of all sources into a single tarball. Times are server-local.

On the server:
```bash
# Collect all telemetry for a time window into a tarball
sudo bash /opt/promptgrimoire/deploy/collect-telemetry.sh \
  --start "2026-03-20 14:00" --end "2026-03-20 16:00"
# Produces: /tmp/telemetry-YYYYMMDD-HHMM.tar.gz
# Prints next-steps with exact commands for local ingestion
```

The script prints next-steps after completion. Follow them in order:
```bash
# 1. Copy tarball to local machine
scp grimoire.drbbs.org:/tmp/telemetry-YYYYMMDD-HHMM.tar.gz /tmp/

# 2. Fetch Beszel metrics (requires SSH tunnel to monitoring hub)
ssh -L 8090:localhost:8090 brian.fedarch.org  # in a separate terminal
uv run scripts/incident_db.py beszel \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" \
  --hub http://localhost:8090 --db incident.db

# 3. Ingest tarball + GitHub data
uv run scripts/incident_db.py ingest /tmp/telemetry-YYYYMMDD-HHMM.tar.gz --db incident.db
uv run scripts/incident_db.py github \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" --db incident.db

# 4. Check provenance manifest
uv run scripts/incident_db.py sources --db incident.db

# 5. Generate review report (extract db-snapshot.json from tarball for counts)
tar xzf /tmp/telemetry-YYYYMMDD-HHMM.tar.gz ./db-snapshot.json -O > /tmp/db-snapshot.json
uv run scripts/incident_db.py review --db incident.db \
  --counts-json /tmp/db-snapshot.json --output report.md
```

### Collection Procedure (Manual Fallback)

If the automated script is unavailable or you need individual sources:

On the server:
```bash
# 1. Save the journal window
sudo journalctl -u promptgrimoire --no-pager -S "HH:MM" -U "HH:MM" > /tmp/incident-YYYYMMDD.log

# 2. Save JSONL (WARNING: covers more than your window — filter in analysis)
sudo cp /opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl /tmp/incident-YYYYMMDD.jsonl

# 3. Save HAProxy log (needs sudo for copy + chmod for scp)
sudo cp /var/log/haproxy.log /tmp/haproxy-YYYYMMDD.log && sudo chmod 644 /tmp/haproxy-YYYYMMDD.log

# 4. Save PG log (needs sudo for copy + chmod for scp)
sudo cp /var/log/postgresql/postgresql-16-main.log /tmp/pglog-YYYYMMDD.log && sudo chmod 644 /tmp/pglog-YYYYMMDD.log

# 5. Check for OOM kills
sudo dmesg | grep -i "oom\|killed"

# 6. Check service status
systemctl status promptgrimoire
```

Pull to local:
```bash
scp "grimoire.drbbs.org:/tmp/incident-YYYYMMDD*" /tmp/
scp "grimoire.drbbs.org:/tmp/haproxy-YYYYMMDD.log" /tmp/
scp "grimoire.drbbs.org:/tmp/pglog-YYYYMMDD.log" /tmp/
```

## Building the Dataset

After collecting telemetry, build the incident database in this order. Each step depends on the previous one.

```bash
# 1. Ingest the tarball (or extracted directory) — creates the DB and loads all log sources
uv run scripts/incident_db.py ingest /tmp/telemetry-YYYYMMDD-HHMM.tar.gz --db /tmp/incident.db

# 2. Fetch GitHub PR metadata (enriches epochs with PR titles/authors)
uv run scripts/incident_db.py github \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" --db /tmp/incident.db

# 3. Verify provenance — check all sources ingested correctly
uv run scripts/incident_db.py sources --db /tmp/incident.db

# 4. Generate the operational review report
uv run scripts/incident_db.py review --db /tmp/incident.db \
  --counts-json /tmp/db-snapshot.json --output /tmp/review.md
```

**Directory ingest:** If the tarball was already extracted, pass the directory instead:
```bash
uv run scripts/incident_db.py ingest /tmp/telemetry-377/ --db /tmp/incident.db
```

**WAL checkpoint:** The SQLite DB uses WAL mode. After a large ingest (~5M+ events), the DB file may appear empty to other connections until the WAL is checkpointed. If you see 0 rows after ingest, run:
```bash
sqlite3 /tmp/incident.db "PRAGMA wal_checkpoint(TRUNCATE)"
```

**Re-ingestion is safe:** SHA256 dedup on the `sources` table means re-running ingest on the same data is a no-op.

**Beszel metrics** (optional, requires SSH tunnel to monitoring hub):
```bash
ssh -L 8090:localhost:8090 brian.fedarch.org  # separate terminal
uv run scripts/incident_db.py beszel \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" \
  --hub http://localhost:8090 --db /tmp/incident.db
```

## Static DB Counts

Snapshot the production database state for the review report. Run on the server or via ssh:

```bash
# On server (peer auth):
sudo -u promptgrimoire psql -At promptgrimoire -c "
SELECT json_build_object(
  'users', (SELECT count(*) FROM \"user\"),
  'workspaces', (SELECT count(*) FROM workspace),
  'courses', (SELECT count(*) FROM course),
  'enrollments', (SELECT count(*) FROM course_enrollment),
  'activities', (SELECT count(*) FROM activity),
  'documents', (SELECT count(*) FROM workspace_document),
  'tags', (SELECT count(*) FROM tag),
  'tag_groups', (SELECT count(*) FROM tag_group),
  'acl_entries', (SELECT count(*) FROM acl_entry),
  'wargame_configs', (SELECT count(*) FROM wargame_config),
  'wargame_teams', (SELECT count(*) FROM wargame_team)
);"

# Via ssh, saving directly to local counts.json:
ssh grimoire.drbbs.org 'sudo -u promptgrimoire psql -At promptgrimoire -c "
SELECT json_build_object(
  '\''users'\'', (SELECT count(*) FROM \"user\"),
  '\''workspaces'\'', (SELECT count(*) FROM workspace),
  '\''courses'\'', (SELECT count(*) FROM course),
  '\''enrollments'\'', (SELECT count(*) FROM course_enrollment),
  '\''activities'\'', (SELECT count(*) FROM activity),
  '\''documents'\'', (SELECT count(*) FROM workspace_document),
  '\''tags'\'', (SELECT count(*) FROM tag),
  '\''tag_groups'\'', (SELECT count(*) FROM tag_group),
  '\''acl_entries'\'', (SELECT count(*) FROM acl_entry),
  '\''wargame_configs'\'', (SELECT count(*) FROM wargame_config),
  '\''wargame_teams'\'', (SELECT count(*) FROM wargame_team)
);"' > counts.json
```

Pass to the review report: `uv run scripts/incident_db.py review --counts-json counts.json`

## Automated Analysis (incident_db.py)

After ingesting a tarball, use `incident_db.py` for cross-source querying. All times are local (server timezone).

```bash
# Provenance manifest — verify what was ingested
uv run scripts/incident_db.py sources --db incident.db

# Cross-source timeline for a window
uv run scripts/incident_db.py timeline \
  --start "2026-03-20 14:00" --end "2026-03-20 16:00" --db incident.db

# Event breakdown by source and level
uv run scripts/incident_db.py breakdown --db incident.db

# Fetch Beszel system metrics (requires SSH tunnel to hub)
uv run scripts/incident_db.py beszel \
  --start "2026-03-20 14:00" --end "2026-03-20 16:00" \
  --hub http://localhost:8090

# Fetch GitHub PR activity for context
uv run scripts/incident_db.py github \
  --start "2026-03-20 00:00" --end "2026-03-20 23:59" --db incident.db

# Generate operational review report (with optional DB counts)
uv run scripts/incident_db.py review --db incident.db --counts-json counts.json --output report.md

# JS timeout epoch analysis — call site breakdown per deploy
uv run scripts/incident_db.py js-timeouts --db incident.db --output js-timeouts.md

# JS timeout analysis with more call sites per epoch
uv run scripts/incident_db.py js-timeouts --db incident.db --top-n 10
```

## JSONL Analysis (Manual)

Use these `jq` commands for ad-hoc queries when `incident_db.py` doesn't cover your need, or when working directly with uningested files.

**The JSONL file is not windowed by default.** It accumulates across restarts. Always filter to your analysis window first.

```bash
# Filter to analysis window (convert your local times to UTC first)
# Example: 14:50–17:20 AEDT = 03:50–06:20 UTC
jq 'select(.timestamp >= "2026-03-16T03:50" and .timestamp <= "2026-03-16T06:20")' \
  /tmp/incident-YYYYMMDD.jsonl > /tmp/incident-filtered.jsonl

# Verify: check line counts
wc -l /tmp/incident-YYYYMMDD.jsonl      # Full file
wc -l /tmp/incident-filtered.jsonl       # Filtered — should be smaller

# Totals by level
jq -r '.level' /tmp/incident-filtered.jsonl | sort | uniq -c | sort -rn

# Error breakdown
jq -r 'select(.level == "error") | .event' /tmp/incident-filtered.jsonl | sort | uniq -c | sort -rn

# Warning breakdown
jq -r 'select(.level == "warning") | .event' /tmp/incident-filtered.jsonl | sort | uniq -c | sort -rn
```

### Known JSONL Limitations

- `exc_info` is often null for DB rollback errors — use journal tracebacks for root cause identification
- INVALIDATE events deduplicate by field values — journal grep may show different counts
- Discord alerting undercounts by 10–50x due to rate limiting/deduplication

## Journal Analysis

The journal has full tracebacks that the JSONL lacks. Use `rtk proxy grep` locally to bypass the rtk hook's output transformation.

```bash
# Error count
rtk proxy grep -c "\[error" /tmp/incident-YYYYMMDD.log

# Error breakdown (extract event name after [error    ] prefix)
rtk proxy grep "\[error" /tmp/incident-YYYYMMDD.log | sed 's/.*\[error *\] //' | cut -d' ' -f1-4 | sort | uniq -c | sort -rn

# Service restarts
rtk proxy grep -E "Stopping|Started|Stopped|Deactivated|Consumed" /tmp/incident-YYYYMMDD.log

# Lines per PID (detect restarts)
rtk proxy grep -c "promptgrimoire\[PID\]" /tmp/incident-YYYYMMDD.log

# DB rollback tracebacks
rtk proxy grep -A 30 "Database session error, rolling back" /tmp/incident-YYYYMMDD.log | rtk proxy grep -E "Error|Exception" | sort | uniq -c | sort -rn

# Pool state events
rtk proxy grep "INVALIDATE" /tmp/incident-YYYYMMDD.log | awk '{print $3, $4}' | cut -d: -f1-2 | sort | uniq -c

# Login rate
rtk proxy grep "Login successful" /tmp/incident-YYYYMMDD.log | awk '{print $3, $4}' | cut -d: -f1-2 | sort | uniq -c

# Unique students
rtk proxy grep "Login successful" /tmp/incident-YYYYMMDD.log | sed 's/.*email=//' | sed 's/,.*//' | sort -u | wc -l
```

## HAProxy Analysis

HAProxy timestamps are server local time (`Australia/Sydney`). No timezone conversion needed when comparing with journal.

```bash
# Total requests by status code (enumerate ALL codes first)
rtk proxy grep -oE ' [0-9]{3} ' /tmp/haproxy-YYYYMMDD.log | sort | uniq -c | sort -rn

# 5xx timeline by minute
rtk proxy grep -E " 5[0-9]{2} " /tmp/haproxy-YYYYMMDD.log | rtk proxy grep -oP '\d{2}/\w{3}/\d{4}:\d{2}:\d{2}' | sort | uniq -c

# 504 gateway timeouts (upload stalls, long requests)
rtk proxy grep " 504 " /tmp/haproxy-YYYYMMDD.log

# 503 backend unavailable (restarts, crashes)
rtk proxy grep " 503 " /tmp/haproxy-YYYYMMDD.log | head -5

# Concurrent connections over time (from ac/fc/bc/sc/rc fields)
# ac=active connections in HAProxy log format
```

### HAProxy Log Format

Configured in `/etc/haproxy/haproxy.cfg`:
```
%ci:%cp [%tr] %ft %b/%s %TR/%Tw/%Tc/%Tr/%Ta %ST %B %CC %CS %tsc %ac/%fc/%bc/%sc/%rc %sq/%bq %hr %hs %{+Q}r
```

Key fields: `%ST` = status code, `%Ta` = total time (ms), `%ac` = active connections, `%{+Q}r` = request path.

### HAProxy History

- Fixed 2026-03-16 ~12:38 AEDT — before this date, no HAProxy log data exists. See `2026-03-16-incident-response.md` for the fix details (corrupted config + AppArmor rsyslog denial).

## PostgreSQL Analysis

**PG logs are UTC.** Convert your analysis window before grepping.

```bash
# All errors and fatals on a specific date (UTC)
rtk proxy grep -E "ERROR|FATAL" /tmp/pglog-YYYYMMDD.log | rtk proxy grep "2026-03-16"

# Filter to afternoon window (example: 15:00–17:20 AEDT = 04:00–06:20 UTC)
rtk proxy grep -E "ERROR|FATAL" /tmp/pglog-YYYYMMDD.log | rtk proxy grep "2026-03-16 0[4-6]"

# Non-checkpoint entries (checkpoints are noise for incident analysis)
rtk proxy grep -v "checkpoint" /tmp/pglog-YYYYMMDD.log | rtk proxy grep -E "ERROR|FATAL"
```

### Known PG Error Patterns

| Pattern | Meaning |
|---------|---------|
| `duplicate key value violates unique constraint "uq_tag_workspace_name"` | Tag duplicate — may indicate race condition or missing app-level check |
| `duplicate key value violates unique constraint "uq_user_student_id"` with `Key (student_id)=()` | Empty string treated as value — schema design issue |
| `FATAL: connection to client lost` | Application dropped a PG connection — correlate with INVALIDATE events in journal |

## System-Level Checks

```bash
# OOM kills
sudo dmesg | grep -i "oom\|killed"

# Service status (PID, memory, uptime)
systemctl status promptgrimoire

# Active PG connections
sudo -u postgres psql -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'promptgrimoire' GROUP BY state;"
```

## Pool Configuration

Current (see `src/promptgrimoire/db/engine.py`): `pool_size=80`, `max_overflow=15` (ceiling: 95 connections). `pool_pre_ping=True`, `pool_recycle=3600`.

Previous configurations:
- `pool_size=10`, `max_overflow=20` (ceiling: 30) — post-commit `a85c1226`
- `pool_size=5`, `max_overflow=10` (ceiling: 15) — original

When analysing INVALIDATE events, check the `size` field to confirm which pool configuration was active. Mixed pool sizes in the same analysis indicate the JSONL spans a config change — filter to the correct window.

**Test environment:** Uses `NullPool` (fresh connection per request, no pooling). Pool contention cannot be reproduced in E2E tests. See `_is_test_environment()` in `engine.py`.

## Known Error Categories

From the 2026-03-16 afternoon analysis (680 afternoon-only errors across 169 students):

| Category | Typical count under load | Severity |
|----------|------------------------|----------|
| JS timeout (NiceGUI UI lag) | High (200+) | User-visible lag |
| Stytch SDK resource leak (unclosed session/connector) | High (200+) | Noise — stable memory |
| NiceGUI UI races (slot deleted, list.index) | Medium (60+) | UI glitches |
| INVALIDATE CancelledError (pool churn) | Very high (1300+) | Latency under load |
| Page load "not ready" warnings | Very high (1700+) | User-visible slow loads |
| DB session rollback | Low-medium (19) | Check root cause — often business logic, not DB |
| LaTeX/export failure | Low (30+) | User-visible export failures |

## Cross-Reference: Related Documents

| Document | Contents |
|----------|----------|
| `docs/postmortems/2026-03-16-incident-response.md` | Triage order, observability gaps, what worked/didn't, HAProxy fix details |
| `docs/postmortems/2026-03-16-afternoon-analysis.md` | Detailed afternoon analysis with corrected counts |
| `docs/postmortems/2026-03-16-new-errors.md` | Errors observed after #360/#361 deploy |
| `docs/postmortems/2026-03-16-proposed-analysis-tools.md` | Proposed automated analysis tooling (under review) |
| `docs/postmortems/2026-03-15-production-oom.md` | Previous day's OOM incident |
| `.claude/skills/incident-analysis/SKILL.md` | General methodology: source provenance, falsification, confidence calibration |
| `docs/postmortems/2026-03-18-page-load-latency-377.md` | #377 page load latency investigation — instrumentation, findings, peer review |
| `.claude/skills/incident-analysis/SKILL.md` | General methodology: source provenance, falsification, confidence calibration |
| `.claude/skills/incident-analysis/CREATION-LOG.md` | Catalogued errors from 2026-03-16 analysis that motivated the methodology |
