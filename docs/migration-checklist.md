# Migration Checklist: NCI to DigitalOcean Cutover

**Purpose:** Migrate PromptGrimoire from NCI Cloud to DigitalOcean with zero data loss.

**Acceptance criteria:** infra-split.AC8.1 (row counts match), infra-split.AC8.3 (smoke test passes).

**Assumptions:**
- NCI app is already stopped (public access down by choice)
- No rehearsal environment — dev is prod
- Old export PDFs are not migrated — students re-export on DO
- Replication is deferred to post-stabilisation (not a day-0 requirement)

---

## Phase 1: Provision DO (while NCI dump runs)

### Step 1: pg_dump on NCI

Start the dump first — it runs while you provision DO.

**Branch A — App is still reachable locally on NCI:**

```bash
# Flush CRDT state before dump (only if app process is running)
curl -sf -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/pre-restart
# Expected: {"initial_count": N}

# Then stop the app
systemctl stop promptgrimoire
```

**Branch B — App is already stopped:**

CRDT state was flushed on the last clean shutdown (the `pre-restart` endpoint is called by `deploy/restart.sh` before every stop). If the app crashed or was killed without a clean stop, some in-flight CRDT edits from the last few seconds before the crash may be lost. For a university annotation tool that has been down for hours, this is acceptable.

**Dump (both branches):**

```bash
sudo -u promptgrimoire pg_dump -Fc -h /var/run/postgresql promptgrimoire \
  -f /home/promptgrimoire/migration.dump

# Gate: dump must be non-empty
[[ -s /home/promptgrimoire/migration.dump ]] \
  || { echo "ERROR: dump is empty — do NOT proceed"; exit 1; }

ls -lh /home/promptgrimoire/migration.dump
sha256sum /home/promptgrimoire/migration.dump
```

**Save NCI row counts** (while dump transfers):

```bash
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
```

### Step 2: Provision DO droplet

**In parallel with dump/transfer.** 16 vCPU / 32 GB, SYD1, Ubuntu 24.04.

Follow `docs/deployment.md` from scratch:

1. PostgreSQL 16
2. Create `promptgrimoire` user, clone repo to `/opt/promptgrimoire`
3. `uv sync`
4. HAProxy with TLS (Let's Encrypt cert for `grimoire.drbbs.org` — get this before DNS switch using DNS-01 challenge or the old cert)
5. TinyTeX
6. systemd units for app + worker (from `deploy/`)
7. `.env` file — copy from NCI and update paths. **Critical settings:**
   ```bash
   FEATURES__WORKER_IN_PROCESS=false
   EXPORT__MAX_CONCURRENT_COMPILATIONS=1
   ```

**Do NOT start the app or worker yet.**

### Step 3: Transfer dump to DO

```bash
scp /home/promptgrimoire/migration.dump do-server:/tmp/

# Verify checksum on DO:
ssh do-server sha256sum /tmp/migration.dump
# Must match NCI checksum from Step 1
```

**Gate:** Checksums match.

---

## Phase 2: Restore and verify (DO stays dark)

### Step 4: pg_restore on DO

```bash
sudo -u promptgrimoire pg_restore -d promptgrimoire \
  -h /var/run/postgresql --clean --if-exists /tmp/migration.dump
```

### Step 5: Row count verification

```bash
sudo -u promptgrimoire psql -d promptgrimoire -tA -c "
ANALYZE;
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

# Compare against NCI counts (transfer nci_counts.txt to DO first):
diff /tmp/nci_counts.txt /tmp/do_counts.txt
# Expected: no output (files identical)
```

**Gate:** `diff` produces no output. Any difference = restore incomplete. Do NOT proceed.

### Step 6: Invalidate old export jobs

Old export PDFs lived in NCI's PrivateTmp — they are gone. Mark all completed exports as expired so the UI doesn't show stale download links:

```sql
UPDATE export_job
SET status = 'expired'
WHERE status = 'completed';
```

### Step 7: Start services on DO (localhost only)

HAProxy stays in maintenance mode — no public traffic reaches the app.

```bash
# Ensure HAProxy is in maintenance mode (blocks public traffic)
echo "set server be_promptgrimoire/app state maint" | socat stdio /run/haproxy/admin.sock

# Start app and worker
systemctl start promptgrimoire promptgrimoire-worker

# Wait for healthcheck
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:8080/healthz && break
  sleep 2
done
# Expected: ok
```

**Gate:** `/healthz` returns `ok` on localhost.

### Step 8: Localhost smoke tests (DO still dark)

All tests run against `localhost:8080`. Public traffic is still blocked.

**8a. Smoke export (CJK + emoji compilation):**

```bash
cd /opt/promptgrimoire
sudo -u promptgrimoire uv run grimoire test smoke-export
# Expected: PDF generated successfully
```

**8b. Mass export check:**

```bash
sudo -u promptgrimoire uv run grimoire export run --scope server --only-errors \
  -o /tmp/migration_export_check
# Expected: all workspaces export successfully (or only pre-existing failures)
```

This is the real verification — every workspace's export pipeline works on DO. `--only-errors` keeps only failures for investigation.

**8c. Verify worker:**

```bash
systemctl status promptgrimoire-worker
# Expected: active (running)

journalctl -u promptgrimoire-worker -n 20
# Expected: worker_ready and poll cycle entries visible
```

**Gate:** smoke-export passes, mass export has no new failures, worker is running. If any fail, investigate on DO. NCI dump is safe — you can re-restore.

---

## Phase 3: Go live

### Step 9: DNS switch

Update `grimoire.drbbs.org` A record to DO droplet IP.

If DNS TTL was lowered in advance (recommended: 60s, 48h before), propagation is fast. If not, propagation takes up to the current TTL (likely 3600s / 1 hour).

### Step 10: Open HAProxy on DO

```bash
echo "set server be_promptgrimoire/app state ready" | socat stdio /run/haproxy/admin.sock
```

### Step 11: Public smoke test

1. Navigate to `https://grimoire.drbbs.org` in a browser
2. Login via magic link or passkey — dashboard loads, workspaces visible
3. Open a workspace — editor loads with CRDT content, annotations visible
4. (If two people available) Real-time collaboration — edits appear within 2-3 seconds

**Gate:** Login, workspace load, and (optionally) collaboration work through the public URL.

### Step 12: Update monitoring

- UptimeRobot: Update healthcheck URL to DO IP
- Beszel: Reconfigure agent/hub for DO server
- Discord alerts: Verify webhook fires from DO (`uv run grimoire admin webhook`)

---

## Phase 4: Stabilisation (next 24 hours)

### Soak period

Observe DO for 24 hours with Discord alerts active before declaring migration complete. Check:

- No ERROR/CRITICAL alerts in Discord
- UptimeRobot shows 100% uptime
- `journalctl -u promptgrimoire --since "1 hour ago" --priority=err` — no errors
- Memory usage stable (Beszel dashboard, `systemctl status promptgrimoire` RSS)

### Restore DNS TTL

After soak period, change `grimoire.drbbs.org` TTL back to 3600s.

### Replication (deferred — not day-0)

Once DO is stable under real load, optionally configure NCI as streaming replication standby per `docs/deployment.md` section 7b. This is a safety net, not a prerequisite.

### Declare migration complete

- [ ] 24h soak period passed with no critical alerts
- [ ] DNS TTL restored to 3600s
- [ ] Monitoring confirmed active on DO
- [ ] NCI old app units disabled (`systemctl disable promptgrimoire`)
