---
source: https://nicegui.io/documentation/section_action_events, NiceGUI 3.6.0 source
fetched: 2026-02-18
summary: NiceGUI 3.x client lifecycle events - on_connect, on_disconnect, on_delete, reconnect_timeout
---

# NiceGUI Client Lifecycle (3.0+)

## Breaking Change in 3.0.0

NiceGUI 3.0.0 changed the semantics of `on_disconnect` and added
`on_delete`. Code written for pre-3.0 that puts final cleanup in
`on_disconnect` will misbehave.

## Lifecycle Events

### App-Level Events

```python
from nicegui import app

app.on_startup(handler)      # NiceGUI started or restarted
app.on_shutdown(handler)     # NiceGUI shut down or restarted
app.on_connect(handler)      # Each client connects (including reconnects)
app.on_disconnect(handler)   # Each client disconnects (including reconnects)
```

All app-level handlers accept an optional `nicegui.Client` parameter.

### Client-Level Events

```python
client.on_connect(handler)     # This specific client connects
client.on_disconnect(handler)  # This specific client disconnects
client.on_delete(handler)      # This specific client is permanently deleted
```

## Event Semantics (3.0+)

### on_disconnect

> *Updated in version 3.0.0: The handler is also called when a client
> reconnects.*

Fires on **every** socket disconnect, including temporary disconnects
during page navigation, tab switches, and network blips. The client
object still exists. NiceGUI starts a `reconnect_timeout` timer.

**Use for:** Transient state updates (e.g., showing user as "away"),
lightweight status changes that are reversible on reconnect.

**Do NOT use for:** Database writes, resource cleanup, final state
persistence, removing shared state that other clients depend on.

### on_delete

> *Added in version 3.0.0*

Fires only after `reconnect_timeout` expires with no reconnection. The
client is being permanently removed. This is the **final** cleanup event.

**Use for:** All heavy cleanup — database writes, CRDT persistence,
CRDT document eviction, presence removal, resource deallocation.

### reconnect_timeout

Configured per page via `@ui.page(reconnect_timeout=...)` or globally.
Default is typically 3.0 seconds. During this window, NiceGUI holds the
client in `Client.instances` waiting for a reconnection.

## Internal Flow

From `client.py`:

```python
def handle_disconnect(self, socket_id):
    # 1. Pop socket, cancel pending delete, decrement connections
    # 2. Invoke all disconnect_handlers via safe_invoke()
    # 3. Invoke all app._disconnect_handlers via safe_invoke()
    # 4. Schedule delete_content() as background task

async def delete_content(self):
    await asyncio.sleep(reconnect_timeout)
    if self._num_connections[document_id] == 0:
        await storage.close_tab(tab_id)
        self.delete()  # <- triggers delete_handlers

def delete(self):
    # 1. Invoke all delete_handlers via safe_invoke()
    # 2. Set/clear asyncio Events
    # 3. remove_all_elements() -> binding.remove()
    # 4. element._handle_delete() for every element
    # 5. outbox.stop()
    # 6. del Client.instances[self.id]
```

### safe_invoke behaviour

- **Sync callables**: called directly on the event loop thread
- **Async callables (coroutine functions)**: `func()` is called to create
  the coroutine, then wrapped in `background_tasks.create()` — runs as a
  background task, does NOT block the event loop
- **Awaitables**: wrapped in a background task directly

## Common Mistakes

### Putting final cleanup in on_disconnect (pre-3.0 pattern)

```python
# WRONG (3.0+): fires on every reconnect, causes data loss
client.on_disconnect(lambda: cleanup_everything())

# RIGHT (3.0+): fires only when client is truly gone
client.on_delete(lambda: cleanup_everything())
```

### Blocking the event loop in handlers

```python
# WRONG: sync handler does I/O
def on_delete():
    db.execute("INSERT ...")  # blocks event loop

# RIGHT: async handler yields to event loop
async def on_delete():
    await db.execute("INSERT ...")  # runs as background task
```

## PromptGrimoire Usage

Our disconnect/cleanup logic in `broadcast.py` should use:

- **`client.on_disconnect`**: (optional) Mark user presence as "away"
- **`client.on_delete`**: Remove presence, persist CRDT state, evict CRDT
  documents, send cursor removal JS to remaining clients
