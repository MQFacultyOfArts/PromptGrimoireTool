# Migration Checklist: NCI to DigitalOcean Cutover

**Purpose:** Zero-data-loss migration of PromptGrimoire from NCI Cloud to DigitalOcean with under 1 hour downtime.

**Acceptance criteria:** infra-split.AC8.1 (row counts match), infra-split.AC8.2 (CRDT spot-check), infra-split.AC8.3 (smoke test passes).

---

## Pre-migration (48+ hours before cutover)

### Step 1: Lower DNS TTL

**Action:** Change `grimoire.drbbs.org` A record TTL from 3600s to 60s. Wait 48 hours for caches to expire.

**Verify:**

```bash
dig grimoire.drbbs.org | grep TTL
# Expected: TTL shows <= 60
```

**Gate:** TTL confirmed at 60s before proceeding to cutover.

---

### Step 2: Provision DO droplet

**Action:** Create 16 vCPU / 32 GB droplet in SYD1, Ubuntu 24.04. Follow `docs/deployment.md` from scratch. Install all services: PostgreSQL, PgBouncer, HAProxy, TinyTeX, app, worker.

**Verify:**

```bash
curl https://<DO_IP>/healthz
# Expected: ok
```

**Gate:** Healthcheck returns `ok` on DO droplet (using test domain or direct IP).

---

### Step 3: Rehearsal migration

**Action:** Full `pg_dump` from NCI, `pg_restore` on DO, verify counts and CRDT integrity.

```bash
# On NCI:
pg_dump -Fc -h /var/run/postgresql -U promptgrimoire promptgrimoire > rehearsal.dump

# Transfer to DO:
scp rehearsal.dump do-server:/tmp/

# On DO:
pg_restore -d promptgrimoire -h /var/run/postgresql -U promptgrimoire rehearsal.dump
```

**Verify:**

- Run row count verification (see Appendix A)
- Run CRDT spot-check (see Appendix B)

**Gate:** All row counts match. CRDT text extraction produces identical output on both servers.

---

## Cutover (~30 minutes)

All times relative to T+0 (start of maintenance window).

| Time | Action | Expected result |
|------|--------|-----------------|
| T-24h | Announce maintenance window via Discord | Users informed |
| T+0 | Flush CRDT state on NCI | `{"initial_count": N}` |
| T+1 | HAProxy maintenance mode on NCI | 503 served to new requests |
| T+2 | Stop app on NCI | Service stopped cleanly |
| T+3 | `pg_dump` on NCI | Dump file created |
| T+4 | Transfer dump to DO | File transferred, sha256 matches |
| T+5 | `pg_restore` on DO | Restore completes without errors |
| T+6 | **VERIFICATION GATE** | Row counts + CRDT check pass |
| T+9 | Start app + worker on DO | Healthcheck returns `ok` |
| T+11 | Update DNS A record to DO IP | DNS propagating |
| T+12 | HAProxy ready on DO | Traffic flowing to app |
| T+16 | **SMOKE TEST GATE** | All smoke tests pass |
| T+21 | Restore DNS TTL to 3600s | TTL back to normal |

### Detailed cutover commands

**T+0 -- Flush CRDT state:**

```bash
curl -sf -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/pre-restart
# Expected: {"initial_count": N}
```

**T+1 -- HAProxy maintenance mode on NCI:**

```bash
echo "set server be_promptgrimoire/app state maint" | socat stdio /run/haproxy/admin.sock
```

**T+2 -- Stop app on NCI:**

```bash
systemctl stop promptgrimoire
```

**T+3 -- pg_dump on NCI:**

```bash
sudo -u promptgrimoire pg_dump -Fc -h /var/run/postgresql promptgrimoire > migration.dump
# Record file size and checksum:
ls -lh migration.dump
sha256sum migration.dump
```

**T+4 -- Transfer to DO:**

```bash
scp migration.dump do-server:/tmp/
# Verify checksum on DO:
ssh do-server sha256sum /tmp/migration.dump
```

**T+5 -- pg_restore on DO:**

```bash
pg_restore -d promptgrimoire -h /var/run/postgresql -U promptgrimoire --clean --if-exists migration.dump
```

**T+6 -- Verification gate:**

Run row count verification (Appendix A) and CRDT spot-check (Appendix B) on both NCI and DO. All counts must match. CRDT text must be identical.

- **IF FAIL:** Do NOT start DO app. DNS stays on NCI. Resume NCI service (see Rollback below).

**T+9 -- Start app + worker on DO:**

```bash
systemctl start promptgrimoire promptgrimoire-worker
# Wait for healthy:
curl -sf http://127.0.0.1:8080/healthz
# Expected: ok
```

**T+11 -- Update DNS:**

Change `grimoire.drbbs.org` A record to DO droplet IP.

**T+12 -- HAProxy ready on DO:**

```bash
echo "set server be_promptgrimoire/app state ready" | socat stdio /run/haproxy/admin.sock
```

**T+16 -- Smoke test gate:**

Run post-migration smoke tests (see Appendix C).

- **IF FAIL:** Revert DNS to NCI IP. Start NCI services. Investigate DO issue.

**T+21 -- Restore DNS TTL:**

Change `grimoire.drbbs.org` A record TTL back to 3600s.

---

## Rollback procedures

### Verification fails at T+6

1. Do NOT start DO app
2. DNS stays pointing at NCI
3. `systemctl start promptgrimoire` on NCI
4. HAProxy ready on NCI: `echo "set server be_promptgrimoire/app state ready" | socat stdio /run/haproxy/admin.sock`
5. Investigate dump/restore failure on DO

### Smoke test fails at T+16

1. Revert DNS A record to NCI IP
2. Start NCI services: `systemctl start promptgrimoire`
3. HAProxy ready on NCI
4. Investigate DO issue offline

### General rollback window

Keep NCI running for 2x original TTL (2 hours) after successful cutover as warm standby. Do not decommission until post-cutover replication is confirmed.

---

## Post-cutover

### Step 1: Configure NCI as streaming replication standby

Follow section 7b in deployment guide to set up NCI as a streaming replication standby for the DO primary.

**Verify:**

```sql
-- On DO (primary):
SELECT * FROM pg_stat_replication;
-- Expected: NCI appears as streaming client
```

**Gate:** Replication lag under 1 MB and state shows `streaming`.

---

### Step 2: Clean up NCI

- Remove old cron jobs from NCI
- Disable app systemd units (keep PostgreSQL running for replication)

---

### Step 3: Update monitoring

- UptimeRobot: Update healthcheck URL to DO IP
- Beszel: Reconfigure agent/hub for DO server
- Discord alerts: Verify alerts fire correctly from DO

**Gate:** Monitoring confirmed active on DO. No stale NCI alerts.

---

### Step 4: Declare migration complete

- All smoke tests passing on DO
- Replication confirmed from DO to NCI standby
- Monitoring pointing at DO
- DNS TTL restored to 3600s
- NCI demoted to standby role

---

## Appendix A: Row count verification

Run on **both** NCI (before dump) and DO (after restore). All counts must match exactly.

### Quick estimate (fast, uses pg statistics)

```sql
-- Estimated row counts from PostgreSQL statistics
-- Good for sanity check; may differ by a few rows from exact counts
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
```

### Exact counts (slower, authoritative)

```sql
-- Exact counts for all 19 application tables
-- Run ANALYZE first on DO to update statistics after restore
ANALYZE;

SELECT 'acl_entry' AS table_name, count(*) FROM acl_entry
UNION ALL SELECT 'activity', count(*) FROM activity
UNION ALL SELECT 'course', count(*) FROM course
UNION ALL SELECT 'course_enrollment', count(*) FROM course_enrollment
UNION ALL SELECT 'course_role', count(*) FROM course_role
UNION ALL SELECT 'export_job', count(*) FROM export_job
UNION ALL SELECT 'export_job_status', count(*) FROM export_job_status
UNION ALL SELECT 'permission', count(*) FROM permission
UNION ALL SELECT 'student_group', count(*) FROM student_group
UNION ALL SELECT 'student_group_membership', count(*) FROM student_group_membership
UNION ALL SELECT 'tag', count(*) FROM tag
UNION ALL SELECT 'tag_group', count(*) FROM tag_group
UNION ALL SELECT 'user', count(*) FROM "user"
UNION ALL SELECT 'wargame_config', count(*) FROM wargame_config
UNION ALL SELECT 'wargame_message', count(*) FROM wargame_message
UNION ALL SELECT 'wargame_team', count(*) FROM wargame_team
UNION ALL SELECT 'week', count(*) FROM week
UNION ALL SELECT 'workspace', count(*) FROM workspace
UNION ALL SELECT 'workspace_document', count(*) FROM workspace_document
ORDER BY table_name;
```

### One-liner for diff comparison

```bash
# On NCI — save counts to file:
sudo -u promptgrimoire psql -d promptgrimoire -tA -c "
SELECT 'acl_entry', count(*) FROM acl_entry
UNION ALL SELECT 'activity', count(*) FROM activity
UNION ALL SELECT 'course', count(*) FROM course
UNION ALL SELECT 'course_enrollment', count(*) FROM course_enrollment
UNION ALL SELECT 'course_role', count(*) FROM course_role
UNION ALL SELECT 'export_job', count(*) FROM export_job
UNION ALL SELECT 'export_job_status', count(*) FROM export_job_status
UNION ALL SELECT 'permission', count(*) FROM permission
UNION ALL SELECT 'student_group', count(*) FROM student_group
UNION ALL SELECT 'student_group_membership', count(*) FROM student_group_membership
UNION ALL SELECT 'tag', count(*) FROM tag
UNION ALL SELECT 'tag_group', count(*) FROM tag_group
UNION ALL SELECT 'user', count(*) FROM \"user\"
UNION ALL SELECT 'wargame_config', count(*) FROM wargame_config
UNION ALL SELECT 'wargame_message', count(*) FROM wargame_message
UNION ALL SELECT 'wargame_team', count(*) FROM wargame_team
UNION ALL SELECT 'week', count(*) FROM week
UNION ALL SELECT 'workspace', count(*) FROM workspace
UNION ALL SELECT 'workspace_document', count(*) FROM workspace_document
ORDER BY 1;
" > /tmp/nci_counts.txt

# On DO — save counts to file:
sudo -u promptgrimoire psql -d promptgrimoire -tA -c "
SELECT 'acl_entry', count(*) FROM acl_entry
UNION ALL SELECT 'activity', count(*) FROM activity
UNION ALL SELECT 'course', count(*) FROM course
UNION ALL SELECT 'course_enrollment', count(*) FROM course_enrollment
UNION ALL SELECT 'course_role', count(*) FROM course_role
UNION ALL SELECT 'export_job', count(*) FROM export_job
UNION ALL SELECT 'export_job_status', count(*) FROM export_job_status
UNION ALL SELECT 'permission', count(*) FROM permission
UNION ALL SELECT 'student_group', count(*) FROM student_group
UNION ALL SELECT 'student_group_membership', count(*) FROM student_group_membership
UNION ALL SELECT 'tag', count(*) FROM tag
UNION ALL SELECT 'tag_group', count(*) FROM tag_group
UNION ALL SELECT 'user', count(*) FROM \"user\"
UNION ALL SELECT 'wargame_config', count(*) FROM wargame_config
UNION ALL SELECT 'wargame_message', count(*) FROM wargame_message
UNION ALL SELECT 'wargame_team', count(*) FROM wargame_team
UNION ALL SELECT 'week', count(*) FROM week
UNION ALL SELECT 'workspace', count(*) FROM workspace
UNION ALL SELECT 'workspace_document', count(*) FROM workspace_document
ORDER BY 1;
" > /tmp/do_counts.txt

# Compare (transfer one file via scp first):
diff /tmp/nci_counts.txt /tmp/do_counts.txt
# Expected: no output (files identical)
```

**Gate:** `diff` produces no output. Any difference means the restore is incomplete — do NOT proceed.

---

## Appendix B: CRDT spot-check

Verifies that binary CRDT state survived dump/restore intact by extracting human-readable text from 3-5 workspaces and comparing between servers.

### Step 1: Pick workspaces to check

```sql
-- Find 5 recently updated workspaces with CRDT state
SELECT id, title, octet_length(crdt_state) AS crdt_bytes
FROM workspace
WHERE crdt_state IS NOT NULL
ORDER BY updated_at DESC NULLS LAST
LIMIT 5;
```

Record the workspace IDs. Use the same IDs on both servers.

### Step 2: Extract CRDT text from each workspace

```bash
# Run on BOTH NCI and DO for each workspace ID
WORKSPACE_ID="<uuid-from-step-1>"

sudo -u promptgrimoire psql -d promptgrimoire -tA -c \
  "SELECT encode(crdt_state, 'base64') FROM workspace WHERE id = '$WORKSPACE_ID'" \
  | python3 -c "
import sys, base64, pycrdt

data = base64.b64decode(sys.stdin.read().strip())
doc = pycrdt.Doc()
doc.apply_update(data)

for key in sorted(doc.keys()):
    obj = doc.get(key)
    if hasattr(obj, '__str__'):
        text = str(obj)[:200]
        print(f'{key}: {text}')
" > /tmp/crdt_${WORKSPACE_ID}.txt
```

### Step 3: Compare output

```bash
# Transfer NCI file to DO (or vice versa), then diff:
diff /tmp/crdt_${WORKSPACE_ID}.txt /tmp/crdt_${WORKSPACE_ID}_do.txt
# Expected: no output (files identical)
```

Repeat for all 5 workspace IDs.

**Gate:** All 5 diffs produce no output. Any difference in CRDT text means binary data was corrupted during transfer — do NOT proceed.

### Troubleshooting

If `python3 -c` fails with `ModuleNotFoundError: No module named 'pycrdt'`:

```bash
# Use the app's virtualenv instead:
sudo -u promptgrimoire /opt/promptgrimoire/.venv/bin/python -c "..."
```

If CRDT bytes differ but text is identical, the binary representation may have been re-encoded. This is acceptable — the semantic content is what matters. If text differs, investigate before proceeding.
