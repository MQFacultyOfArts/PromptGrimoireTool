---
name: run-incident-investigation
description: Run a production incident investigation end-to-end — collect telemetry, build dataset, generate review report, write postmortem. Operationalises the incident-analysis methodology skill with concrete commands for PromptGrimoire's infrastructure.
user-invocable: true
---

# Run Incident Investigation

Operational workflow for investigating a PromptGrimoire production incident. Uses `collect-telemetry.sh`, `incident_db.py`, and the incident-analysis methodology skill.

**Announce:** "I'm using the run-incident-investigation skill to investigate the incident."

## Prerequisites

- Read `docs/postmortems/incident-analysis-playbook.md` — the full reference
- Read `scripts/incident/AGENTS.md` — tooling contracts
- Activate the `incident-analysis` methodology skill (for Phases 3–7)

## Step 1: Establish the Window

Ask the user for:
1. **When did the incident start?** (local time, AEST/AEDT)
2. **When was it resolved?** (or "ongoing")
3. **What was the symptom?** (downtime, errors, slow pages, OOM)
4. **Is the service currently up?**

Convert times to UTC for tooling. The server is `Australia/Sydney` — AEDT is UTC+11 (Oct–Apr), AEST is UTC+10 (Apr–Oct).

Record in a TaskCreate:
```
Incident window: YYYY-MM-DD HH:MM – HH:MM AEST/AEDT (HH:MM – HH:MM UTC)
Symptom: [what the user reported]
```

## Step 2: Collect Telemetry

Give the user **one command at a time**. Do not give a list.

### 2a. Run collect-telemetry.sh on the server

```bash
# SSH to server
ssh grimoire.drbbs.org

# Run collection (full date + time, local timezone — script converts to UTC)
# Source: deploy/collect-telemetry.sh lines 4-5, 54-57, 70-71
sudo bash /opt/promptgrimoire/deploy/collect-telemetry.sh \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM"
```

Wait for the user to provide the output. The script prints the tarball path and next-steps.

### 2b. Copy tarball to local machine

```bash
scp grimoire.drbbs.org:/tmp/telemetry-YYYYMMDD-HHMM.tar.gz /tmp/
```

### 2c. (Optional) Fetch Beszel metrics

Only if the user has the SSH tunnel set up:
```bash
# In a separate terminal:
ssh -L 8090:localhost:8090 brian.fedarch.org

# Then fetch:
uv run scripts/incident_db.py beszel \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" \
  --hub http://localhost:8090 --db /tmp/incident.db
```

## Step 3: Build the Dataset

These commands run locally. Execute them sequentially — each depends on the previous.

```bash
# 1. Ingest tarball
uv run scripts/incident_db.py ingest /tmp/telemetry-YYYYMMDD-HHMM.tar.gz --db /tmp/incident.db

# 2. Fetch GitHub PR metadata
uv run scripts/incident_db.py github \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" --db /tmp/incident.db

# 3. Verify provenance
uv run scripts/incident_db.py sources --db /tmp/incident.db
```

**Check the sources output.** Every expected source must appear. If any are missing, investigate before proceeding.

## Step 4: Generate the Review Report

```bash
# Extract db-snapshot.json from tarball
tar xzf /tmp/telemetry-YYYYMMDD-HHMM.tar.gz ./db-snapshot.json -O > /tmp/db-snapshot.json

# Generate report
uv run scripts/incident_db.py review --db /tmp/incident.db \
  --counts-json /tmp/db-snapshot.json --output /tmp/review.md
```

Read the generated report. It contains:
- Epoch timeline (deploy boundaries)
- Per-epoch error breakdown, HAProxy status codes, resource usage
- User activity metrics
- Cross-epoch trends with anomaly detection

## Step 5: Investigate

Now apply the `incident-analysis` skill methodology:

1. **Source inventory** — already done by `sources` command. Verify the provenance table.
2. **Enumerate before drilling** — the review report has category breakdowns. Use them.
3. **Form hypotheses** — each finding must follow the well-formed finding template.
4. **Cross-source reconciliation** — trace significant events across JSONL, journal, HAProxy, PG.

### Useful ad-hoc queries

```bash
# Timeline of events in a window
uv run scripts/incident_db.py timeline \
  --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM" \
  --level error --db /tmp/incident.db

# Event breakdown by type
uv run scripts/incident_db.py breakdown --db /tmp/incident.db

# JS timeout analysis (if relevant)
uv run scripts/incident_db.py js-timeouts --db /tmp/incident.db --output /tmp/js-timeouts.md

# Raw SQL for anything else
sqlite3 /tmp/incident.db "SELECT ..."
```

### Direct log queries (when the DB isn't enough)

```bash
# JSONL — filter by time window (timestamps are UTC)
jq -r 'select(.timestamp >= "YYYY-MM-DDTHH:MM" and .timestamp < "YYYY-MM-DDTHH:MM")' /tmp/file.jsonl

# HAProxy — status code breakdown (local time)
grep "DD/Mon/YYYY:HH:MM" /tmp/haproxy.log | grep -oE ' [0-9]{3} ' | sort | uniq -c | sort -rn

# PG log — error search (UTC timestamps)
grep "^YYYY-MM-DD HH:MM" /tmp/pglog.log | grep -i error
```

## Step 6: Write the Postmortem

Create: `docs/postmortems/YYYY-MM-DD-<slug>.md`

Structure:
```markdown
# Incident: <title>

**Date:** YYYY-MM-DD
**Duration:** HH:MM – HH:MM AEST/AEDT
**Severity:** [service down | degraded | error spike]
**Detection:** [UptimeRobot | user report | Beszel alert | log review]

## Source Inventory

[Provenance manifest table from Step 3]

## Timeline

[Epoch-based timeline from review report, annotated with findings]

## Findings

[Well-formed findings per incident-analysis skill template]

## Contributing Factors

[Causal chain, not root cause]

## Action Items

| # | Action | Issue | Priority |
|---|--------|-------|----------|
| 1 | ... | #NNN | P0/P1/P2 |
```

## Rules

- **One server command at a time.** Give one, wait for output, give the next.
- **Never assume service state.** Check `systemctl status` before and after.
- **All numbers need provenance.** Command that produced it, source, filter, timezone.
- **Do not skip the sources check.** Missing sources invalidate the analysis.
- **Convert all times.** The user thinks in AEST/AEDT. The tooling uses UTC. Always show both.
- **Do not push fixes during investigation.** Investigate first, fix second. Separate branches.
