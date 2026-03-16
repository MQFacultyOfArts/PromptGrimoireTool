# Incident Response Commands: 2026-03-16

*Reference for future incidents. Documents what worked, what didn't, and where logs live.*

## Investigation Discipline

Lessons from the 2026-03-16 investigation (reviewed by Codex):

1. **Verify numbers from the initial report immediately.** The initial framing said "600 students" and Discord showed "5 DB errors". Actual: 49 students, 52 errors. Both wrong by 10x. First action after getting journal logs: count the actual events.
2. **Phrase findings as a failure chain, not a single root cause.** Separate "service degradation cause" from "data loss mechanism" — they have different confidence levels. Don't say "confirmed root cause" when you mean "confirmed that this link in the chain is supported by evidence."
3. **Don't assume architecture.** The investigator assumed workspaces were shared between students. They're per-student (cloned). This led to a wrong theory about multi-user races that had to be corrected. Cite evidence for architectural claims.
4. **PG log timestamps are UTC.** AEDT = UTC+11. The 11:08 AEDT incident is at 00:08 UTC in PG logs. This caught us out initially.
5. **Check ALL error types, not just the ones in your hypothesis.** The initial focus on DB rollback errors missed that `QueuePool limit` errors, JS timeouts, "not ready" warnings, slot deletion errors, and `list.index` errors were all present. A full `grep "\[error" | sort | uniq -c` early would have revealed the complete picture faster.
6. **Discord webhooks severely undercount.** 5 alerts for 52 errors. Don't trust alert count as error count. Always check the journal.

## Log Sources

### Application Journal (WORKS)

```bash
# Full journal for time window (WARNING: can be huge — 141K lines for 15 min under load)
sudo journalctl -u promptgrimoire --no-pager -S "HH:MM" -U "HH:MM"

# Errors only (follow mode)
sudo journalctl -u promptgrimoire -f -p err

# Save to file for offline analysis
sudo journalctl -u promptgrimoire --no-pager -S "HH:MM" -U "HH:MM" > /tmp/incident.log
```

**Useful grep patterns (use rtk proxy grep for raw output locally):**
```bash
# DB session errors (the generic wrapper — look at traceback for actual exception)
grep "\[error    \] Database session error" incident.log

# Specific exception types
grep "UniqueViolationError\|QueuePool limit\|CancelledError\|TimeoutError" incident.log

# Pool state (INVALIDATE shows checked_in/checked_out/overflow)
grep "INVALIDATE" incident.log

# Page load failures
grep "not ready after" incident.log

# Login rate
grep "Login successful" incident.log | sed 's/.*Mar .. //' | cut -d: -f1-2 | sort | uniq -c

# CRDT/DB divergence (data loss indicator)
grep "CRDT tag.*not in DB\|CRDT group.*not in DB" incident.log

# Unique student count
grep "Login successful" incident.log | sed 's/.*email=//' | sed 's/,.*//' | sort -u | wc -l

# NiceGUI UI errors
grep "slot belongs to has been deleted\|list.index" incident.log

# Stytch SDK leaks
grep "Unclosed client session\|Unclosed connector" incident.log
```

### HAProxy (BROKEN as of 2026-03-16)

```bash
# HAProxy logs to syslog (local0), NOT systemd journal
# This returned nothing:
sudo journalctl -u haproxy --no-pager -S "HH:MM" -U "HH:MM"  # DOES NOT WORK

# HAProxy log file location:
ls -la /var/log/haproxy*

# On 2026-03-16, haproxy.log was 0 bytes (rotated at midnight, nothing logged today)
# Log format is configured in /etc/haproxy/haproxy.cfg:
#   log /dev/log local0
#   log-format "%ci:%cp [%tr] %ft %b/%s %TR/%Tw/%Tc/%Tr/%Ta %ST %B %CC %CS %tsc %ac/%fc/%bc/%sc/%rc %sq/%bq %hr %hs %{+Q}r"
#
# TODO: Fix rsyslog routing for local0 → /var/log/haproxy.log
# Check: /etc/rsyslog.d/ for haproxy config

# Previous day's log (if it exists):
sudo grep "pattern" /var/log/haproxy.log.1
```

### PostgreSQL (NOT in journal — has its own log file)

```bash
# PostgreSQL logs to its own file, NOT systemd journal
sudo journalctl -u postgresql --no-pager -S "HH:MM" -U "HH:MM"  # DOES NOT WORK

# PG log location:
ls -la /var/log/postgresql/
# Current log: /var/log/postgresql/postgresql-16-main.log

# IMPORTANT: PG timestamps are UTC. AEDT = UTC+11.
# For AEDT 11:00-11:15, search UTC 00:00-00:15
sudo grep '2026-03-16 00:0[89]\|2026-03-16 00:1[012345]' /var/log/postgresql/postgresql-16-main.log

# PG backend PIDs let you correlate concurrent operations on the same data
```

### System-Level

```bash
# Check for OOM kills
sudo dmesg | grep -i "oom\|killed"

# Check memory at incident time
sudo journalctl -k -S "HH:MM" -U "HH:MM" | grep -i memory

# Service restarts
sudo journalctl -u promptgrimoire --no-pager -S "HH:MM" -U "HH:MM" | grep -i "start\|stop\|restart"

# systemd service status
systemctl status promptgrimoire
```

### UptimeRobot

- Checks `/healthz` every 5 min via HTTP GET
- `/healthz` returns `PlainTextResponse("ok")` WITHOUT checking DB (`__init__.py:303-304`)
- Will NOT alert for DB failures, pool exhaustion, or event loop saturation
- Only alerts if the process is completely dead or HAProxy returns 503

## Observability Gaps Found During This Incident

1. **HAProxy logging broken** — rsyslog not routing local0 to haproxy.log. Zero HTTP-level data for the incident.
2. **`/healthz` is blind to DB** — returns 200 even when all DB operations are failing
3. **PostgreSQL logs not checked** — need to verify PG log location and access
4. **Discord alerting deduplicates/rate-limits** — 52 DB errors appeared as 5 Discord alerts. Actual error count was 10x what was reported.
5. **Pool diagnostics at DEBUG level** — CHECKOUT/CHECKIN events not logged in production (only INVALIDATE at WARNING). During incidents, we can't see pool checkout patterns.
6. **No request-level metrics** — no way to know how many requests succeeded vs failed, or what HTTP status codes students received
7. **rtk hook mangles grep output** — use `rtk proxy grep` for raw output when analysing logs locally

## Triage Order for Future Incidents

When students report problems, gather data in this order:

### Immediate (during incident, < 5 min)

1. **Is the process alive?** `systemctl status promptgrimoire` — check PID, memory, uptime
2. **Tail errors live:** `sudo journalctl -u promptgrimoire -f -p err` — see what's failing in real time
3. **Check Beszel dashboard:** SSH tunnel to brian.fedarch.org (`ssh -L 8090:localhost:8090`), look at CPU/memory/disk graphs
4. **Pool state (if you can run a quick query):**
   ```sql
   SELECT state, count(*) FROM pg_stat_activity
   WHERE datname = 'promptgrimoire' GROUP BY state;
   ```

### Soon after (within 30 min, while logs are fresh)

5. **Save the journal window:** `sudo journalctl -u promptgrimoire --no-pager -S "HH:MM" -U "HH:MM" > /tmp/incident-YYYYMMDD.log`
6. **Save PG logs (timestamps in UTC, AEDT-11):** `sudo cp /var/log/postgresql/postgresql-16-main.log /tmp/pglog-YYYYMMDD.log`
7. **Save HAProxy logs (if working):** `sudo cp /var/log/haproxy.log /tmp/haproxy-YYYYMMDD.log`
8. **Check structlog JSONL:** `sudo tail -500 /opt/promptgrimoire/logs/sessions/promptgrimoire.jsonl | jq 'select(.level == "error")'` — machine-parseable, has user_id/workspace_id fields
9. **Ask students to screenshot browser console** (F12 → Console tab) and Network tab if they still have the tab open

### Post-incident analysis

10. **CRDT/DB divergence audit** — compare CRDT tag sets against DB tag sets for affected workspaces
11. **Query affected workspaces** — use workspace IDs from PG log to identify affected students:
    ```sql
    SELECT w.id, w.title, u.email
    FROM workspace w
    JOIN acl_entry a ON a.workspace_id = w.id
    JOIN "user" u ON u.id = a.user_id
    WHERE w.id IN ('<uuid1>', '<uuid2>', ...);
    ```
12. **Check Stytch dashboard** — login attempts, rate limiting, SSO failures
13. **Beszel historical graphs** — CPU/memory/disk/network for the incident window
14. **Check Discord webhook delivery** — compare alert count to actual error count (expect significant undercounting due to rate limiting)

### Data sources NOT available on this server

| Source | Why | Fix |
|---|---|---|
| HAProxy access logs | rsyslog not routing local0 to haproxy.log | Fix rsyslog config |
| PG logs in journal | PG logs to own file, not systemd | Documented — use `/var/log/postgresql/` |
| System metrics at incident time | Ephemeral (`/proc`, `vmstat`) | Beszel captures some; consider adding Prometheus node exporter |
| Browser-side errors | Need student cooperation | Add client-side error reporting (e.g., `window.onerror` → server endpoint) |
| Request-level metrics (latency, status codes, throughput) | No request instrumentation | Add Starlette middleware or HAProxy stats |
| NiceGUI websocket connection count | Not exposed | Consider adding periodic logging of `app.state.clients` or equivalent |
| structlog JSONL | May be in wrong directory (#359) | Verify path, ensure rotation |

## HAProxy Log Fix (2026-03-16 ~12:45 AEDT)

**Problem:** `haproxy.log` was 0 bytes on 2026-03-16. No HTTP-level data for incident response.

**Diagnosis steps (run in order, document output at each step):**

1. Check rsyslog config exists:
   ```bash
   cat /etc/rsyslog.d/49-haproxy.conf
   ```
   Output: Config exists, has both brace-style and if/then routing rules. Looks correct.

2. Check chroot socket exists:
   ```bash
   ls -la /var/lib/haproxy/dev/log
   ```
   Output: Socket exists (`srw-rw-rw-`), created Mar 15 15:21.

3. Check apparmor denials:
   ```bash
   sudo journalctl -u rsyslog --since "1 hour ago" | grep -i denied
   ```
   Output: No denials.

4. Test that logging works:
   ```bash
   curl -sk https://localhost/ > /dev/null 2>&1; sleep 2; sudo tail -1 /var/log/haproxy.log
   ```
   Output: Empty — nothing written.

5. Validate HAProxy config:
   ```bash
   sudo haproxy -c -f /etc/haproxy/haproxy.cfg
   ```
   Output: **CONFIG IS CORRUPTED.** Line 1 reads `yesglobal` instead of `global`. All directives fail as "out of section". The running HAProxy process loaded from the pre-corruption config, but the file on disk is broken. `haproxy -c` fails, meaning a reload would also fail.

   **Root cause of logging failure:** The running HAProxy process may have loaded before the corruption, OR the corruption happened during initial setup and HAProxy was never restarted to pick it up. Either way, the config is invalid.

6. Fix: HAProxy config had `yesglobal` instead of `global` on line 1. Fixed with nano, validated with `haproxy -c`. Reloaded HAProxy.

7. After reload, `sendmsg()/writev() failed in logger #1: Permission denied (errno=13)`. Apparmor `rsyslogd` profile blocking chroot socket access ("disconnected path"). Known Ubuntu bug [LP#2138647](https://bugs.launchpad.net/ubuntu/+source/haproxy/+bug/2138647).

8. Fix: Added `flags=(attach_disconnected)` to profile declaration in `/etc/apparmor.d/usr.sbin.rsyslogd` line 9:
   ```
   profile rsyslogd /usr/sbin/rsyslogd flags=(attach_disconnected) {
   ```
   Then: `sudo apparmor_parser -r /etc/apparmor.d/usr.sbin.rsyslogd && sudo systemctl restart rsyslog`

**Fix applied:** 2026-03-16 ~12:43 AEDT
**Validated:** `curl -sk https://grimoire.drbbs.org/healthz` produced a log line in `/var/log/haproxy.log` with full custom log format (client IP, status code, timing, request path). Websocket upgrades (101) also logging.

## What Worked

- Application journal captured full tracebacks with timestamps and context vars (user_id, workspace_id, request_path)
- Pool INVALIDATE warnings included connection state (`checked_in`, `checked_out`, `overflow`)
- CRDT reconciliation logged tag removals with workspace and user IDs
- Discord webhook alerting fired (even if undercounting)
- Login events with email, auth method, user_id logged consistently
