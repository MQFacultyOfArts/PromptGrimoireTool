---
source: pycrdt source code (_awareness.py) + codebase investigation
fetched: 2026-02-12
library: pycrdt
summary: Awareness API for ephemeral presence state (cursors, selections, disconnect cleanup)
---

# pycrdt Awareness API Reference

## Overview

`Awareness` manages ephemeral presence state (cursors, selections, user info) for connected clients. Unlike `Doc` data which persists, Awareness state is transient and auto-cleaned on disconnect.

## Class: `Awareness`

```python
from pycrdt import Awareness, Doc

doc = Doc()
awareness = Awareness(doc, outdated_timeout=30000)
```

### Constructor

```python
Awareness(ydoc: Doc, *, outdated_timeout: int = 30000) -> None
```

- `ydoc`: The Doc instance this Awareness is associated with (shares `client_id`)
- `outdated_timeout`: Milliseconds before a client is considered disconnected (default: 30s)

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `client_id` | `int` | Local client identifier (from Doc) |
| `meta` | `dict[int, dict[str, Any]]` | Per-client metadata: `{client_id: {"clock": int, "lastUpdated": int}}` |
| `states` | `dict[int, dict[str, Any]]` | Per-client state dicts (the actual presence data) |

### State Management

```python
# Set entire local state
awareness.set_local_state({
    "client_id": "user-1",
    "name": "Alice",
    "color": "#2196F3",
    "cursor": 42,
    "selection": {"start_char": 10, "end_char": 25},
})

# Update a single field (incremental)
awareness.set_local_state_field("cursor", 55)

# Get current local state
state = awareness.get_local_state()  # -> dict | None

# Clear state (signals removal to peers)
awareness.set_local_state(None)

# Remove specific remote clients
awareness.remove_awareness_states(client_ids=[123, 456], origin="cleanup")
```

### Observation

```python
def on_awareness_change(topic: str, event_data: tuple[dict[str, Any], Any]) -> None:
    changes, origin = event_data
    # changes = {"added": [int], "updated": [int], "removed": [int]}
    for client_id in changes["added"]:
        state = awareness.states.get(client_id)
        print(f"New client: {state}")
    for client_id in changes["removed"]:
        print(f"Client left: {client_id}")

# Subscribe (returns subscription ID)
sub_id = awareness.observe(on_awareness_change)

# Unsubscribe
awareness.unobserve(sub_id)
```

**Two event topics:**
- `"change"` — fired when state content actually differs
- `"update"` — fired on any update, even if state is identical

### Encoding/Decoding for Transport

```python
# Encode local state for sending over network
update: bytes = awareness.encode_awareness_update([awareness.client_id])

# Apply received remote update
awareness.apply_awareness_update(update, origin="remote")
```

**With pycrdt message framing:**
```python
from pycrdt import create_awareness_message, YMessageType

# Wrap for transport
message = create_awareness_message(update)

# Parse received message
if message[0] == YMessageType.AWARENESS:
    update = message[1:]
    awareness.apply_awareness_update(update, origin="remote")
```

### Timeout/Cleanup Lifecycle

**Critical: Cleanup is NOT automatic.** You must call `start()`.

```python
# Start the background cleanup loop
await awareness.start()

# ... work with awareness ...

# Stop the cleanup loop
await awareness.stop()
```

**Cleanup internals:**
- Check interval: `timeout / 10` = **1.5 seconds** (at default 30s timeout)
- Local renewal: if `(now - lastUpdated) >= timeout / 2` (15s), auto-renews local state
- Remote cleanup: if `(now - lastUpdated) >= timeout` (30s), removes client
- `stop()` raises `RuntimeError` if `start()` was never called

### Integration with Doc

- Both share the same `client_id`
- Doc stores **persistent** data (highlights, notes, comments)
- Awareness stores **ephemeral** data (cursors, selections, user names/colours)
- No automatic sync between them — must encode/send awareness updates separately

## Gotchas

1. **No automatic broadcast.** `set_local_state()` updates locally only. You must `encode_awareness_update()` and send over your transport layer.

2. **Clock versioning.** Remote updates with a lower clock value than stored are silently ignored. Same clock + `None` state = accepted removal.

3. **Remote can't remove local.** If a remote peer sends a removal for your `client_id`, it's ignored (clock increments instead).

4. **Must call `start()`.** Without it, disconnected clients are never cleaned up.

5. **`stop()` before `start()` crashes.** Raises `RuntimeError`.

6. **State is unvalidated dicts.** pycrdt does no schema validation — add your own.

7. **JSON-serialised internally.** States are JSON-encoded in the binary wire format. Keep state small.

## PromptGrimoire Usage

File: `src/promptgrimoire/crdt/annotation_doc.py`

```python
# Line 70: Initialised
self.awareness = Awareness(self.doc)

# Lines 172-174: Client registration sets initial state
self.awareness.set_local_state({
    "client_id": client_id,
    "name": name,
    "color": color,
})

# Lines 511-576: Three helper methods exist but are NEVER CALLED
# update_cursor(), update_selection(), clear_cursor_and_selection()
# These are seams for the CSS Highlight API migration (Phase 5)
```

**Current state:** Awareness instance exists. `register_client()` sets initial state. But:
- No `await awareness.start()` — cleanup not enabled
- No observer callbacks — changes not propagated to UI
- Cursor/selection methods defined but unwired
- `unregister_client()` does NOT clear awareness state (only clears Doc metadata)
