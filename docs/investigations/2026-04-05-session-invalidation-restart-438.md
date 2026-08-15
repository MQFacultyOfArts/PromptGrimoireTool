# Spike Preregistration: Session Invalidation on Restart (#438 Re-investigation)

Date: 2026-04-05
Investigator: Gemini CLI
Status: Phase 1 — Root Cause Investigation & Spike Preregistration

## Incident Context
The original #438 cross-user session contamination incident (users seeing other users' data) occurred **specifically after a server restart**. The introduction of `_invalidate_all_sessions()` — which clears `auth_user` from `FilePersistentDict` on SIGTERM — correlated with the bug disappearing.

However, the architecture has since evolved to support horizontal scaling with a Redis-backed session store. In a multi-instance Redis deployment, `_invalidate_all_sessions()` is currently causing all sessions to be invalidated globally on any single instance's restart/deployment, which defeats the purpose of distributed sessions.

## Differential Baseline (Restart Boundary)
Before modifying the session invalidation logic, we must establish the differential baseline for how session data behaves across process boundaries (restarts):

1. **Single-Instance (`FilePersistentDict`)**: Writes are lazy. A SIGTERM could race with disk flushes, meaning a restarted instance could read stale JSON files, potentially restoring a different user's session if cookie/session mappings were reused or improperly tracked.
2. **Multi-Instance (`RedisPersistentDict`)**: Redis is the authoritative store, and writes are immediate (not lazy). A restarting instance doesn't corrupt Redis state; it simply disconnects and reconnects.

## The Core Question
Why invalidate sessions on restart at all in multi-instance mode?

If the original "data leak" issue was specific to `FilePersistentDict` races with process death, then removing `_invalidate_all_sessions()` (or skipping the Redis DEL) in multi-instance mode should be completely safe.

## Preregistered Spike (Test Plan)

We must rigorously demonstrate that removing global session invalidation in multi-instance mode does not reintroduce the #438 contamination bug.

### Spike Objective
Prove that a user, rejoining after their laptop sleeps for 20 minutes (and thereby ending up routed to a different server instance upon waking up), will see **their data and only their data**.

### Methodology (RED/GREEN Falsification)
1. **Setup**: Deploy a multi-instance (at least 2 instances) configuration using `RedisPersistentDict`.
2. **State Creation**: Authenticate User A on Instance 1. Authenticate User B on Instance 2. Populate their workspaces with distinct data.
3. **Simulate Sleep**: Disconnect User A's websocket (simulate laptop sleep). Wait for NiceGUI to prune the inactive client.
4. **Simulate Restart/Routing**: Restart Instance 1 (or manipulate HAProxy) to guarantee User A's subsequent reconnection request routes to Instance 2.
5. **Reconnection & Verification**: User A wakes up and sends a request (with their original session cookie) to Instance 2.
6. **Assertion**:
   - User A is correctly authenticated on Instance 2.
   - User A sees **only** User A's data.
   - User B sees **only** User B's data.
   - `app.storage.user` resolves correctly for both users without any identity overlap.

### Success Criteria
If the spike demonstrates perfect session isolation upon cross-instance reconnection, we can confidently conclude that:
1. The #438 data leak was a `FilePersistentDict` artefact.
2. We can safely skip Redis DEL in `_invalidate_all_sessions()` for multi-instance deployments.
3. This unblocks Phase 2 UAT for the horizontal scaling rollout.
