# Post-Mortem: 2026-03-16 Service Degradation and Data Loss During Live Class

*Written: 2026-03-16*
*Status: Investigation complete. Remediation pending.*

## Summary

PromptGrimoire production (grimoire.drbbs.org) experienced ~7 minutes of service degradation and confirmed data loss during a live LAWS class on 2026-03-16 11:08-11:14 AEDT. 49 students logged in; an unknown subset experienced "cannot access the app" errors. Two students had confirmed data loss (tags + highlights removed by CRDT reconciliation). The server did not crash — PID 885075 remained stable throughout.

## Timeline (AEDT)

| Time | Event |
|------|-------|
| 11:00:50 | First student login. 30 students log in within 60 seconds. |
| 11:01:04 | Burst of 12 aiohttp "Unclosed client session" warnings (Stytch SDK resource leak during rapid logins) |
| 11:08:38 | **First DB error.** `UniqueViolationError` on `uq_tag_workspace_name` — duplicate tag INSERT. |
| 11:08:41-11:09:27 | 14 UniqueViolation errors on tag/group creation across multiple workspaces |
| 11:09:28 | **Pool saturation begins.** `checked_in=0 checked_out=15 overflow=10/10`. First QueuePool timeout errors. |
| 11:09:28-11:10:29 | 61 pool INVALIDATE events (all `exception=CancelledError`, not IntegrityError). 4 QueuePool timeout errors. |
| 11:10:29-11:11:48 | Continued UniqueViolation errors + tag_creation_failed + list.index errors |
| 11:11:48-11:12:03 | **206 "Response for /annotation not ready after 3.0 s" warnings** (48 in one second at 11:11:57). Event loop saturated. |
| 11:11:57-11:11:59 | PG log: `Connection reset by peer`, `Broken pipe`, `FATAL: connection to client lost` |
| 11:12:02 | First confirmed CRDT scrub: workspace `9d8a4947`, tag `db6e44b0` removed from CRDT (not in DB) |
| 11:13:50 | Second confirmed CRDT scrub: workspace `62624529`, tag `6c0360d8` removed from CRDT |
| 11:14:39-11:14:59 | Second smaller wave of UniqueViolation errors |
| ~11:15 | Students report service is working again |

## Failure Chain

This is a confirmed chain of events with varying confidence levels at each link.

### 1. Trigger: duplicate tag/group INSERTs (HIGH confidence)

Concurrent tag and tag-group creation operations on per-student workspaces generated INSERTs that violated unique constraints (`uq_tag_workspace_name`, `uq_tag_group_workspace_name`).

**Evidence:** 31 `uq_tag_workspace_name` violations and 8 `uq_tag_group_workspace_name` violations in the PostgreSQL log (`/var/log/postgresql/postgresql-16-main.log`, 00:08-00:15 UTC). 15 unique workspaces affected across 24 PG backend connections. All group collisions were `"New group"` on workspace `ba1a8a16`.

### 2. Amplifier: pool saturation from cancellation cascade (HIGH confidence for pool saturation, MODERATE for the bridge)

Each `UniqueViolationError` caused: (a) `get_session()` logs a rich traceback + fires Discord webhook, (b) session rollback. Separately, client disconnects (students refreshing after seeing errors) generated `CancelledError` on in-flight DB operations, and these cancellations triggered pool INVALIDATE events. All 61 INVALIDATE events in the journal show `exception=CancelledError`, not `IntegrityError` — the uniqueness failures preceded the cancellation/invalidation storm but did not directly invalidate connections. Pool reached 15/15 checked out.

### 3. Impact: event loop saturation -> service degradation (HIGH confidence)

The event loop was processing 52 DB error tracebacks, 61 pool INVALIDATE events, Discord webhook HTTP calls, and ~30 websocket connections simultaneously. New `/annotation` page loads could not complete within 3 seconds.

**Evidence:** 206 "Response for /annotation not ready after 3.0 seconds" warnings. 22 "JavaScript did not respond within 1.0 s" errors. 37 "The parent element this slot belongs to has been deleted" errors.

### 4. Data loss: CRDT reconciliation removed orphaned tags (MODERATE confidence)

Tags that were created in the CRDT (client-side) but whose DB INSERT was rolled back were removed by `_reconcile_crdt_with_db()` (`annotation_doc.py:870-878`) on subsequent page loads. Any highlights applied using those tags were lost.

**Evidence:** Two confirmed CRDT scrub events. Full scope of data loss is not known from server logs alone.

## What Worked

- Server stayed up (no OOM, no crash, PID 885075 stable)
- Discord webhook alerting fired (though severely undercounted -- 5 alerts for 52 errors)
- PostgreSQL was healthy throughout (no resource limits, no deadlocks, checkpoints normal)
- Deploy script with HAProxy drain/maint operational
- Unit test e-stop correctly blocked a deploy with failing tests

## What Failed

- **Tag/group creation has no conflict handling at the DB layer.** Expected business logic races surface as unhandled exceptions that cascade into full service degradation.
- **Discord alerting severely undercounted.** 5 alerts for 52 errors (~10x undercount).
- **`/healthz` is blind to DB state** (`__init__.py:303-304`). Returns `PlainTextResponse("ok")` unconditionally.
- **HAProxy logging broken.** `haproxy.log` was 0 bytes on the day of the incident. Fixed during investigation.
- **No request-level metrics.** No way to determine what HTTP status codes students received.

## Theories Falsified

- **Pool exhaustion as primary cause:** Pool timeouts are secondary, starting 47 seconds after the first UniqueViolation.
- **Stytch SDK leak reduced DB pool:** aiohttp sessions are HTTP to Stytch API, not database connections. No causal link.
- **PostgreSQL-level fault:** PG log shows no deadlocks, no connection limits, no restarts. All errors are application-level.

## Action Items

### Immediate (fix the trigger)

- [ ] #360: Fix tag/group duplicate-name handling at DB layer
- [ ] #361: Deduplicate "New group" default name + caller UX
- [ ] #362: Tag/group rename/save paths need duplicate handling

### Short-term (fix observability)

- [x] **Fix HAProxy rsyslog routing** -- DONE (2026-03-16 ~12:43 AEDT). Config corrupted + apparmor `attach_disconnected`. See incident-response.md.
- [ ] #363: Expected business exceptions should not hit generic get_session() ERROR/Discord path
- [ ] Add DB health check to `/healthz`
- [ ] Fix structlog JSONL log file path (#359)

### Medium-term (reduce blast radius)

- [ ] #364: Activity start/clone idempotency
- [ ] #365: Tag import atomicity
- [ ] #366: Capacity hardening -- pool sizing, metrics, load testing for ~1.5k students
- [ ] #367: UX -- onboarding flow + server health signalling
- [ ] Pre-restart client notification (#355)

## Related Documents

- Investigation: `docs/postmortems/2026-03-16-investigation.md`
- Incident response runbook: `docs/postmortems/2026-03-16-incident-response.md`
- Previous postmortem: `docs/postmortems/2026-03-15-production-oom.md`
