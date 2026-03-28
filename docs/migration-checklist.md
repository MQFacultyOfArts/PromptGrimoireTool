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
