---
source: https://github.com/zauberzeug/nicegui/issues/5110, https://github.com/zauberzeug/nicegui/issues/4521, https://github.com/zauberzeug/nicegui/issues/2502, https://github.com/zauberzeug/nicegui/issues/5595, https://github.com/zauberzeug/nicegui/discussions/1046
fetched: 2026-03-28
library: nicegui
summary: Production memory management, client lifecycle, storage durability, and known leak patterns for NiceGUI 3.9.0
---

# NiceGUI Production Memory Management

Research conducted 2026-03-28 for PromptGrimoire running NiceGUI 3.9.0
with ~190 concurrent users behind HAProxy on a 4 vCPU / 8GB server.

## 1. Storage Internals (FilePersistentDict)

`app.storage.user` is backed by `FilePersistentDict`:
- One JSON file per browser session: `.nicegui/storage/storage-user-<uuid>.json`
- Browser gets a secure session cookie containing a UUID mapped to the file
- **Writes are async and lazy**: `backup()` calls `background_tasks.create_lazy()`
- The `@await_on_shutdown` decorator tags the backup coroutine, but only works
  if NiceGUI's own `teardown()` runs. A `SIGTERM` + `systemctl restart` may
  kill the process before lazy tasks flush.

### SIGTERM Data Loss (confirmed in production 2026-03-28)

`PersistentDict.pop("auth_user")` triggers `on_change` -> `backup()` ->
`create_lazy()`. The lazy task was still pending when `systemctl restart`
killed the process. On-disk files retained stale `auth_user` keys.

**Fix (PR #441)**: Use `dict.pop()` to bypass `on_change`, then call
`filepath.write_text()` synchronously.

### Storage File Accumulation

`.nicegui/storage/storage-user-*.json` files are **never automatically
cleaned up**. They accumulate indefinitely. Tab storage has a 30-day max
age, but user storage does not.

**Recommendation**: Add a cron or deploy-time cleanup:
```bash
find .nicegui/storage/ -name "storage-user-*.json" -mtime +7 -delete
```

## 2. Client Lifecycle & Memory

### Client.instances

- `Client.instances` is a class-level `dict[str, Client]` holding ALL clients
- Each browser tab = one Client with a **full server-side UI element tree**
- `Client.prune_instances(client_age_threshold=60.0)` removes stale clients

### Cleanup sequence

1. Browser disconnects -> `handle_disconnect()` clears tab_id
2. After `reconnect_timeout` seconds -> Client marked for deletion
3. `prune_instances()` removes clients older than `client_age_threshold`
4. GC collects the Client object **IF no circular references remain**

### reconnect_timeout impact

Set to 30.0s in PromptGrimoire (`ui.run(reconnect_timeout=30.0)`).
Every disconnected client (tab switch, network blip, page refresh)
holds its full UI tree for 30s. With 190 users churning, significant
accumulation. Upstream recommends 10-15s for production.

**Trade-off**: Lower timeout = faster cleanup but worse UX on flaky
networks. Higher timeout = easier for DoS (disconnect/reconnect spam).

## 3. Known Memory Leak Patterns

### Circular reference cycles (#5110) — HIGH IMPACT

NiceGUI elements hold parent <-> child circular references that block
CPython's reference-counting GC. The cyclic GC must collect them,
and its pause time is O(n) in active client count.

At 190 users: potentially multi-second GC pauses blocking ALL users.

Fix in recent NiceGUI versions removes some cycles, but not all.
Monitor with `gc.get_stats()` and `gc.collect()` timing.

Source: https://github.com/zauberzeug/nicegui/issues/5110

### ui.refreshable leak (#2502) — MEDIUM IMPACT

`ui.refreshable` can leak element references across refresh cycles.
Old elements may not be properly dereferenced.

**PromptGrimoire uses ui.refreshable in**:
- `pages/annotation/tab_bar.py`
- `pages/annotation/header.py`
- `pages/annotation/pdf_export.py`
- `pages/annotation/tag_management_rows.py`
- `pages/navigator/_cards.py`
- `pages/navigator/_search.py`
- `pages/annotation/sharing.py`
- `pages/courses.py`
- `pages/logviewer.py`

Source: https://github.com/zauberzeug/nicegui/issues/2502

### ui.timer leak on immediate disconnect (#5595) — MEDIUM IMPACT

`ui.timer` instances leak when a client disconnects immediately after
timer creation, before the timer's first tick.

**PromptGrimoire uses ui.timer in**: (same files as ui.refreshable,
plus auth callback redirect timers)

Source: https://github.com/zauberzeug/nicegui/issues/5595

### High memory in SPA patterns (#4521)

Single-page-app patterns (one `@ui.page` route doing lots of dynamic
UI) accumulate more element trees per client than multi-page patterns.

Source: https://github.com/zauberzeug/nicegui/issues/4521

### Fatal leak when reload=True (#5127)

Running with `reload=True` in production causes a fatal memory leak.
PromptGrimoire correctly uses `reload=settings.app.reload` (False in
production).

Source: https://github.com/zauberzeug/nicegui/discussions/5127

## 4. Production Architecture Constraints

### Single-process model

NiceGUI **does not support multiple uvicorn workers**. It runs as a
single-process, single-threaded async application. This means:

- Single GC thread — pauses block all users
- No horizontal scaling within one instance
- CPU-bound work (LaTeX compilation) blocks the event loop

### Horizontal scaling requirements

Multiple NiceGUI instances require:
- **Sticky sessions** (HAProxy `balance source` or cookie-based)
- **Redis storage backend** (`NICEGUI_REDIS_URL`) for shared state
- Independent `.nicegui/storage/` directories per instance

### Practical concurrency ceiling

Researcher estimate: ~300-400 concurrent users per instance before
GC pauses and memory pressure become untenable, depending on page
complexity and element count per client.

Source: https://github.com/zauberzeug/nicegui/discussions/1539

## 5. Configuration Reference

| Parameter | Default | Production | Notes |
|-----------|---------|------------|-------|
| `reconnect_timeout` | 3.0 | 10-15 | Balances UX vs memory |
| `message_history_length` | 1000 | 500-1000 | Messages buffered for reconnect |
| `binding_refresh_interval` | 0.1 | 0.1-0.5 | Higher = less CPU, more latency |
| `reload` | True | **False** | Fatal leak if True in production |
| `prod_js` | True | True | Use production Vue/Quasar builds |
| `storage_secret` | None | Required | For `app.storage.user` and `.browser` |

Source: https://nicegui.io/documentation/section_configuration_deployment
