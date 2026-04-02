# Horizontal Scaling: Multi-Instance NiceGUI with Workspace-Affinity Routing

**GitHub Issue:** #466

## Summary

PromptGrimoire currently runs as a single NiceGUI process on a 16-core/32GB server. With 1100 students submitting an assignment on 2 April 2026, a single instance is insufficient. This design scales the application horizontally by running N NiceGUI processes on the same server, each on a different port, fronted by HAProxy.

The central challenge is NiceGUI's real-time collaboration model: CRDT state for an open workspace lives in memory on the instance that owns it. Cross-instance CRDT sync is explicitly a non-goal — the Hocuspocus project documents that Redis Pub/Sub for CRDT is an HA pattern, not a scaling pattern, and true horizontal scaling requires document sharding. Instead, workspace affinity is implemented at the application layer: when a user opens a workspace, the instance atomically claims ownership in Redis using `SETNX`. If the user lands on the wrong instance, the application issues an HTTP redirect with a `Set-Cookie` override that tells HAProxy to route subsequent requests (including the WebSocket) to the owning instance. This keeps all collaborators on the same workspace on the same instance, so the existing CRDT broadcast, persistence, and presence tracking require no changes. Redis also provides shared login sessions across instances (via NiceGUI's built-in Redis storage backend) and a Pub/Sub channel for cross-instance ban notifications.

## Definition of Done

PromptGrimoire runs multiple NiceGUI instances on the same server, behind HAProxy with cookie-based sticky sessions and application-level workspace affinity, supporting 1100 concurrent students for an assignment due 2 April 2026.

1. **Multiple instances:** N NiceGUI processes on different ports, managed by systemd templated units.
2. **Workspace-affinity routing:** HAProxy uses `leastconn` + cookie sticking for all traffic. Application middleware uses Redis `SETNX` to claim workspace ownership per-instance and redirects users to the correct instance when they land on the wrong one.
3. **Shared sessions:** Redis installed, `NICEGUI_REDIS_URL` configured, so login state (`app.storage.user`) persists across instances.
4. **Cross-instance ban:** Redis Pub/Sub broadcast on ban, all instances subscribe and disconnect matching clients.
5. **Deployment:** `deploy/restart.sh` updated to manage multiple instances (rolling restart). Supersedes #419 blue/green deploy.

**Out of scope:** Cross-instance CRDT sync, thundering herd mitigation (separate ticket), cross-instance presence display, dedicated CRDT service (Hocuspocus/y-sweet).

## Acceptance Criteria

### horizontal-scaling-466.AC1: Multiple instances run independently
- **horizontal-scaling-466.AC1.1 Success:** N systemd units start on consecutive ports, each responding to `/healthz`
- **horizontal-scaling-466.AC1.2 Success:** Each instance logs with its own `INSTANCE_ID` in structured output
- **horizontal-scaling-466.AC1.3 Failure:** Instance that fails to bind port exits with clear error (not silent hang)

### horizontal-scaling-466.AC2: Workspace affinity routes collaborators to one instance
- **horizontal-scaling-466.AC2.1 Success:** First user to open a workspace claims it via Redis `SETNX`; subsequent users on the same workspace are redirected to the owning instance
- **horizontal-scaling-466.AC2.2 Success:** Redirect response includes `Set-Cookie: SERVERID={owner}` and HAProxy routes the follow-up request correctly
- **horizontal-scaling-466.AC2.3 Success:** Last client disconnects from workspace → Redis ownership key deleted → next visitor claims fresh
- **horizontal-scaling-466.AC2.4 Edge:** Instance crashes → workspace ownership TTL expires → next visitor claims on a surviving instance, loads CRDT from DB
- **horizontal-scaling-466.AC2.5 Edge:** User opens 2 workspaces in 2 tabs on different instances → both tabs function; if one tab's WebSocket reconnects to the wrong instance, NiceGUI rebuilds the page from DB without user action
- **horizontal-scaling-466.AC2.6 Edge:** Two users open the same unowned workspace simultaneously on different instances → only one `SETNX` succeeds, the other user is redirected

### horizontal-scaling-466.AC3: Login state persists across instances
- **horizontal-scaling-466.AC3.1 Success:** User logs in on instance A, is redirected to instance B for a workspace → remains authenticated (no re-login)
- **horizontal-scaling-466.AC3.2 Success:** `app.storage.user["auth_user"]` readable from any instance via Redis
- **horizontal-scaling-466.AC3.3 Failure:** Rolling restart invalidates sessions on restarted instance → user transparently re-authenticates via stored Redis state on surviving instance

### horizontal-scaling-466.AC4: Ban disconnects user across all instances
- **horizontal-scaling-466.AC4.1 Success:** `uv run grimoire admin ban <email>` on any instance → user disconnected from ALL instances within seconds
- **horizontal-scaling-466.AC4.2 Success:** Pub/Sub message received by all subscribing instances; each checks local `client_registry` and calls `disconnect_user()` for matching clients
- **horizontal-scaling-466.AC4.3 Failure:** Pub/Sub subscriber temporarily disconnected → ban still enforced on next page load via DB check (`is_user_banned()` in `page_route`)

### horizontal-scaling-466.AC5: Rolling restart with zero downtime
- **horizontal-scaling-466.AC5.1 Success:** `restart.sh` restarts all instances sequentially; at no point are all instances down simultaneously
- **horizontal-scaling-466.AC5.2 Success:** Users on a restarting instance are drained (`/api/pre-restart`), reconnect to surviving instances via HAProxy, and resume without data loss
- **horizontal-scaling-466.AC5.3 Success:** Workspace ownership re-claimed by surviving instances after restarted instance's TTL expires; CRDT loaded from DB

## Glossary

- **NiceGUI**: Python web UI framework. Each running NiceGUI process is an "instance." Uses socket.io for real-time browser-server communication and persists session data via file-backed or Redis-backed storage (`app.storage.user`).
- **socket.io**: Transport layer NiceGUI uses for bidirectional browser-server communication. Requests go to `/socket.io/` (no workspace ID in path), which is why URL-based HAProxy routing doesn't work — a key reason for application-level affinity.
- **CRDT (Conflict-free Replicated Data Type)**: Data structure for annotation workspace content, enabling real-time multi-user collaboration without locking. Implemented via `pycrdt`. Lives in memory on the owning instance, periodically flushed to PostgreSQL.
- **Workspace affinity**: Routing guarantee that all users of the same workspace are served by the same NiceGUI instance. Allows the existing single-instance CRDT model to work without cross-instance sync.
- **`SETNX` (SET if Not eXists)**: Redis atomic operation that sets a key only if it doesn't exist. Used for workspace ownership claims — only one instance can succeed, preventing split ownership.
- **Sticky sessions**: Load-balancer feature routing all requests from the same browser to the same backend, implemented via the `SERVERID` cookie.
- **`leastconn`**: HAProxy algorithm routing new connections to the backend with fewest active connections. Used for initial placement before workspace affinity kicks in.
- **`PersistenceManager`**: Internal component (`crdt/persistence.py`) that debounce-saves CRDT state to PostgreSQL. Extended to release Redis workspace ownership on last client disconnect.
- **`page_route` decorator**: Application middleware (`pages/registry.py`) wrapping every page handler. Currently enforces ban checks; workspace affinity middleware added here.
- **`client_registry`**: Internal component (`auth/client_registry.py`) tracking active NiceGUI clients by user for session disconnection. Extended to respond to cross-instance ban Pub/Sub.
- **Systemd templated unit**: Single service file (e.g., `promptgrimoire@.service`) instantiated multiple times with different parameters (e.g., `promptgrimoire@0`, `promptgrimoire@1`).
- **Hocuspocus**: Reference Yjs collaboration server. Cited because it explicitly warns Redis Pub/Sub for CRDT is an HA pattern, not horizontal scaling — justifying the workspace-affinity approach.

## Architecture

### Overview

N NiceGUI processes run on the same 16-core/32GB DigitalOcean server, each on a different port (8080, 8081, ...). HAProxy sits in front with `balance leastconn` and cookie-based sticky sessions (`cookie SERVERID insert nocache`). Redis provides three services: NiceGUI session sharing (`NICEGUI_REDIS_URL`), atomic workspace ownership claims (`SETNX`), and ban broadcast (Pub/Sub).

Workspace affinity is application-level, not HAProxy-level. When a user opens a workspace, middleware checks Redis for which instance owns it. If unowned, the current instance claims it atomically via `SETNX`. If owned by another instance, middleware returns an HTTP redirect with `Set-Cookie: SERVERID={owner}`, causing HAProxy to route subsequent requests to the correct instance. The cookie is not marked `indirect` in HAProxy — the app can override it.

This avoids cross-instance CRDT sync entirely. All collaborators on the same workspace are routed to the same instance, so the existing single-instance CRDT broadcast (`pages/annotation/broadcast.py`), persistence (`crdt/persistence.py`), and presence tracking (`_RemotePresence`) work unchanged.

### Why Not HAProxy URL Hashing

HAProxy `balance uri` was evaluated and rejected. NiceGUI uses socket.io, which sends requests to `/socket.io/` (no workspace ID in path). With multi-tab usage, each workspace page load overwrites the browser-wide `SERVERID` cookie, causing socket.io reconnections in other tabs to route to the wrong instance. Application-level routing with cookie override is multi-tab safe: the cookie changes only on explicit redirect, and existing WebSocket connections persist on their TCP connection.

### Why Not Cross-Instance CRDT Sync

The Hocuspocus project (reference Yjs production server) explicitly warns: "All messages will be handled on all instances. If you are trying to reduce CPU load by spawning multiple servers, you should NOT connect them via Redis." Redis Pub/Sub for CRDT is an HA pattern, not a horizontal scaling pattern. True horizontal scaling requires document sharding — which is what workspace affinity provides.

### Data Flow

```
Browser → HAProxy (leastconn + SERVERID cookie)
  → NiceGUI instance (port 808N)
    → Workspace affinity middleware
      → Redis SETNX check
        → If wrong instance: redirect with Set-Cookie
        → If correct instance: proceed to page handler
    → Page handler loads CRDT from DB (if not cached)
    → Socket.io establishes on same instance (follows cookie)
    → CRDT updates broadcast to local clients only
    → PersistenceManager debounce-saves to PostgreSQL (5s)
```

### Redis Architecture

Single Redis instance on localhost. Three distinct uses:

| Use | Mechanism | Key pattern | Lifecycle |
|-----|-----------|-------------|-----------|
| Session sharing | `NICEGUI_REDIS_URL` (NiceGUI built-in) | NiceGUI-managed | NiceGUI-managed |
| Workspace ownership | Direct `redis.asyncio` client, `SETNX` | `ws_owner:{workspace_id}` | TTL ~60s, refreshed by heartbeat while clients connected. Explicit `DEL` on eviction. TTL handles crash recovery. |
| Ban broadcast | Direct `redis.asyncio` Pub/Sub | Channel: `bans`, keys: `ban:{user_id}` | Explicit `DEL` on unban. Pub/Sub for real-time notification. |

### Multi-Tab Behaviour

When a user has multiple workspaces open in tabs:
- All tabs share one browser-wide `SERVERID` cookie
- Tab 1 opens workspace A on instance 1 — WebSocket established on TCP connection
- Tab 2 opens workspace B owned by instance 2 — redirect overwrites cookie to `s2`
- Tab 1's WebSocket persists (TCP connection, unaffected by cookie change)
- If tab 1's WebSocket drops and reconnects, it follows the new cookie to instance 2
- Instance 2 loads workspace A from DB, rebuilds the page (NiceGUI's normal reconnection flow)
- The ~5s CRDT debounce means DB state is near-current

### Cross-Instance Ban

1. Admin runs `uv run grimoire admin ban <email>` — hits any instance
2. Instance writes `ban:{user_id}` to Redis, publishes user ID to `bans` Pub/Sub channel
3. All instances subscribe to `bans` channel, check local `client_registry`, disconnect matching clients via existing `disconnect_user()` mechanism
4. Page-load ban check (`is_user_banned()` in `page_route` decorator) remains DB-authoritative — Redis is notification layer only

### Log Level Tuning

Production log level changes from `DEBUG` to `INFO`. Configurable via `LOG_LEVEL` env var for incident investigation. `INSTANCE_ID` added to structlog's `add_global_fields()` processor so log lines are distinguishable across instances. All instances write to systemd journal (one pipe).

## Existing Patterns

### Patterns Followed

- **`page_route` middleware** (`pages/registry.py`): Workspace affinity check added as middleware, following the existing ban-check pattern in `page_route`.
- **`client_registry`** (`auth/client_registry.py`): Ban disconnect mechanism unchanged. Pub/Sub listener calls existing `disconnect_user()`.
- **`PersistenceManager`** (`crdt/persistence.py`): Unchanged. Workspace eviction (`evict_workspace()`) extended to release Redis ownership.
- **`AppConfig`** (`config.py`): `INSTANCE_ID` added as new config field following existing pydantic-settings pattern.
- **`logging_config.setup_logging()`**: `INSTANCE_ID` added alongside existing `pid`, `branch`, `commit` global fields.

### New Pattern: Direct Redis Client

NiceGUI's `app.storage.general` syncs lazily (periodic full-dict flush) and cannot provide atomic operations. Workspace ownership and ban broadcast use a direct `redis.asyncio` client for `SETNX`, Pub/Sub, and TTL management. This is a new infrastructure dependency — the `redis` package is already pulled in by `nicegui[redis]`.

## Implementation Phases

**Phase 1 is a spike.** Prove the architecture works before writing production code. If the spike fails, we find out in hours, not days.

<!-- START_PHASE_1 -->
### Phase 1: Architecture Spike

**Goal:** Prove multi-instance + Redis SETNX + redirect works end-to-end on the local dev machine.

**Components:**
- Minimal test script: start 2 NiceGUI instances on different ports with `NICEGUI_REDIS_URL`
- Redis `SETNX` claim for a test workspace
- HTTP redirect with `Set-Cookie: SERVERID` override
- Verify: user on instance A opens workspace owned by instance B, gets redirected, lands on instance B

**Dependencies:** Redis installed locally (`apt install redis-server` or `docker run redis`)

**Spike must prove:**
1. Two instances redirect correctly based on Redis SETNX ownership
2. Socket.io WebSocket reconnects cleanly after redirect (no broken page state)
3. CRDT loads from DB on the target instance and is editable
4. Simultaneous access to same workspace from different instances: one wins SETNX, other redirects

**Abort criteria:** If the redirect breaks NiceGUI's socket.io session in a way that requires manual page refresh (not automatic reconnection), or if SETNX race produces data divergence, abandon this design and fall back to Approach A (simple cookie sticking, no workspace affinity).

**Done when:** All 4 spike criteria verified manually on local dev machine.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Redis Infrastructure + Config

**Goal:** Add Redis client, configuration, and instance identity to the app.

**Components:**
- `INSTANCE_ID` field in `AppConfig` (`config.py`) — defaults to `s0` for single-instance dev
- `LOG_LEVEL` field in `AppConfig` — defaults to `DEBUG` for dev, `INFO` for production
- Redis client module (`src/promptgrimoire/redis_client.py`) — async connection pool, `SETNX`/`GET`/`DEL`/`EXPIRE` helpers, Pub/Sub subscription
- `INSTANCE_ID` added to `add_global_fields()` in `logging_config.py`
- Log level configuration in `setup_logging()`

**Dependencies:** Phase 1 (spike validates approach)

**Done when:** `INSTANCE_ID` appears in structured log output. Redis client connects and performs `SETNX`/`GET` round-trip. Log level configurable via env var. Tests verify config loading and Redis operations.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Workspace Affinity Middleware

**Goal:** Route users to the instance that owns the workspace they're opening.

**Components:**
- Workspace affinity middleware in `pages/registry.py` or dedicated module — checks Redis ownership on annotation page load
- `SETNX` claim on first access, `DEL` on eviction, TTL refresh heartbeat
- HTTP redirect with `Set-Cookie: SERVERID={owner}` when on wrong instance
- Integration with `PersistenceManager.evict_workspace()` — release Redis ownership on last client disconnect

**Dependencies:** Phase 2 (Redis client and config)

**Done when:** Integration tests pass: two NiceGUI instances (local processes), workspace claimed by instance A, request to instance B returns redirect. Eviction releases ownership. TTL expiry handles crash.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Cross-Instance Ban

**Goal:** Banning a user disconnects them from all running instances.

**Components:**
- Redis Pub/Sub subscriber in app startup — listens on `bans` channel
- Ban handler: on message, check local `client_registry`, call `disconnect_user()` if user is connected
- Ban publisher in `admin ban` CLI command — write `ban:{user_id}` key + publish to `bans` channel
- DB remains source of truth for ban state (`is_user_banned()` unchanged)

**Dependencies:** Phase 2 (Redis client)

**Done when:** Integration test: ban user on instance A, verify disconnect fires on instance B's client registry. Pub/Sub message delivery verified.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Systemd + HAProxy Configuration

**Goal:** Production infrastructure for running N instances.

**Components:**
- `deploy/promptgrimoire@.service` — systemd templated unit with per-instance `APP__PORT`, `INSTANCE_ID`, `NICEGUI_STORAGE_PATH`, `NICEGUI_REDIS_URL`
- HAProxy backend configuration — `leastconn` + `cookie SERVERID insert nocache` + health checks on each instance port
- Redis server configuration (`redis.conf` if tuning needed, default is likely fine)
- PgBouncer `max_client_conn` increase for N instances × pool size

**Dependencies:** Phases 2-4 (application code complete)

**Done when:** `systemctl start promptgrimoire@{0..4}` brings up 5 instances. HAProxy routes to all backends. Health checks pass. Redis connected.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Rolling Restart

**Goal:** Deploy new code without downtime across all instances.

**Components:**
- `deploy/restart.sh` rewrite — iterate instances sequentially: drain (`/api/pre-restart`), wait for connection count 0, restart, wait for `/healthz`, next instance
- Worker restart after all app instances healthy
- Workspace ownership TTL handles instance restart: claims expire, surviving instances re-claim on user reconnect

**Dependencies:** Phase 5 (systemd units running)

**Done when:** `restart.sh` successfully restarts all instances sequentially with zero user-visible errors. Supersedes #419 blue/green deploy.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Multi-Instance E2E Tests

**Goal:** Automated tests proving multi-instance behaviour works.

**Components:**
- Test fixture: start 2 NiceGUI instances as subprocesses (different ports) + Redis + local HAProxy
- E2E tests (application layer):
  - Workspace SETNX claim and redirect
  - Multi-tab: open 2 workspaces, verify both function
  - Ban on instance A disconnects user on instance B
  - Instance restart: workspace ownership expires and re-claims
- E2E tests (HAProxy layer):
  - Cookie sticking: verify `SERVERID` cookie set on first request, subsequent requests follow it
  - Health check failover: stop one instance, verify HAProxy routes to survivors
  - Cookie override: verify app-set `Set-Cookie: SERVERID` changes routing
- CI: `redis-server` and `haproxy` service containers in GitHub Actions, `requires_redis` and `requires_haproxy` markers

**Dependencies:** Phases 3-5 (workspace affinity, ban, and HAProxy config)

**Done when:** All multi-instance E2E tests pass in CI with 2 local NiceGUI instances + Redis + HAProxy.
<!-- END_PHASE_7 -->

## Additional Considerations

**Capacity planning:** At ~200 users per instance, 5-6 instances handle 1100 students. Start with 5, add more by starting another systemd unit and adding a server line to HAProxy.

**PgBouncer tuning:** Each instance runs QueuePool (size 20 + overflow 10 = 30 connections). 5 instances = 150 connections. PgBouncer `max_client_conn` and PostgreSQL `max_connections` must be increased accordingly. The server has ample resources (16 vCPU / 32 GB RAM).

**Lazy `app.storage.general` sync:** NiceGUI's Redis-backed `app.storage.general` uses periodic full-dict flush, not per-write sync. This is fine for session data but NOT for workspace ownership claims (requires atomicity). All ownership operations use direct Redis client.

**SETNX TTL calibration:** The ~60s TTL is a starting point. Too short causes ownership thrash (claims expire during active use); too long leaves stale claims after a crash. The spike (Phase 1) must empirically test TTL behaviour under simulated load. Heartbeat refresh interval should be TTL/3 (~20s).

**Instance failure:** If an instance crashes, its workspace ownership claims expire via Redis TTL (~60s). Users reconnect to surviving instances (HAProxy health check removes the dead backend). The surviving instance claims the workspace fresh and loads CRDT from DB.

**Future: true workspace affinity at HAProxy level.** If socket.io adds per-connection identifiers accessible to HAProxy (e.g., via query parameters), URL-based routing could replace the application-level redirect. Not needed now.
