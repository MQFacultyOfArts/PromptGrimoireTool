---
source: https://docs.yjs.dev/api/document-updates, https://y-crdt.github.io/pycrdt/
fetched: 2025-01-14
summary: pycrdt WebSocket sync patterns for real-time collaboration
---

# pycrdt WebSocket Synchronization

pycrdt provides Python bindings for Yrs (Rust port of Yjs). This guide covers syncing documents over WebSocket for real-time collaboration.

## Core Sync Concepts

Document updates are binary-encoded, compressed messages that are:
- **Commutative**: Can be applied in any order
- **Associative**: Can be grouped in any way
- **Idempotent**: Can be applied multiple times safely

## Basic Sync Pattern

```python
from pycrdt import Doc, Text

# Create two documents
doc1 = Doc()
doc1["text"] = text1 = Text("Hello")

doc2 = Doc()
doc2["text"] = text2 = Text()

# Get full state from doc1
update = doc1.get_update()

# Apply to doc2 - now they're synced
doc2.apply_update(update)
print(str(text2))  # "Hello"
```

## Efficient Differential Sync

Exchange only missing data using state vectors:

```python
from pycrdt import Doc, Text

doc1 = Doc()
doc1["text"] = Text("Hello")

doc2 = Doc()
doc2["text"] = Text()

# Get state vectors
sv1 = doc1.get_state()
sv2 = doc2.get_state()

# Compute diffs - only missing changes
diff1_to_2 = doc1.get_update(sv2)  # What doc2 is missing
diff2_to_1 = doc2.get_update(sv1)  # What doc1 is missing

# Apply diffs
doc1.apply_update(diff2_to_1)
doc2.apply_update(diff1_to_2)
```

## Observing Changes for Sync

```python
from pycrdt import Doc, Text, TransactionEvent

doc = Doc()
doc["text"] = text = Text()

def on_update(event: TransactionEvent):
    update: bytes = event.update
    # Send update over WebSocket to other clients
    # websocket.send(update)

doc.observe(on_update)

# Changes trigger the observer
text += "Hello"  # on_update called with binary update
```

## Async Event Iteration

```python
import asyncio
from pycrdt import Doc, Text

async def sync_updates(doc: Doc, websocket):
    async with doc.events() as events:
        async for event in events:
            update: bytes = event.update
            await websocket.send(update)
```

## NiceGUI + pycrdt WebSocket Integration

### Server-Side Document Manager

```python
from pycrdt import Doc, Text
from nicegui import app, ui
import asyncio

# Shared document (server-side)
shared_doc = Doc()
shared_doc["content"] = shared_text = Text()

# Track connected clients
clients: dict[str, any] = {}

@app.on_connect
async def on_connect(client):
    clients[client.id] = client
    # Send current state to new client
    update = shared_doc.get_update()
    await ui.run_javascript(
        f'window.applyUpdate(new Uint8Array({list(update)}))'
    )

@app.on_disconnect
def on_disconnect(client):
    clients.pop(client.id, None)

def broadcast_update(update: bytes, origin_client_id: str = None):
    """Send update to all clients except origin."""
    for client_id, client in clients.items():
        if client_id != origin_client_id:
            ui.run_javascript(
                f'window.applyUpdate(new Uint8Array({list(update)}))',
                client=client
            )

# Observe document changes
def on_doc_update(event):
    broadcast_update(event.update)

shared_doc.observe(on_doc_update)
```

### Client-Side JavaScript Handler

```python
from nicegui import ui

ui.add_head_html('''
<script>
// Client-side CRDT state (simplified - in practice use y-websocket)
window.localDoc = null;

window.applyUpdate = function(updateArray) {
    // Apply server update to local state
    console.log('Received update:', updateArray.length, 'bytes');
    // Update UI accordingly
    document.dispatchEvent(new CustomEvent('crdt-update', {
        detail: { update: updateArray }
    }));
};

window.sendUpdate = function(update) {
    // Send local changes to server
    // This would call back to Python
};
</script>
''')
```

### Full Spike Example: Two-Tab Sync

```python
from nicegui import app, ui
from pycrdt import Doc, Text

# Shared state
doc = Doc()
doc["text"] = text = Text()
clients = {}

def broadcast(update: bytes, exclude=None):
    for cid, client in clients.items():
        if cid != exclude:
            # Update other clients
            pass

@ui.page('/')
async def main():
    client_id = app.storage.tab.get('client_id', str(id(app.storage.tab)))
    app.storage.tab['client_id'] = client_id
    clients[client_id] = app.storage.tab

    # Text display bound to CRDT
    label = ui.label().bind_text_from(app.storage.tab, 'content')

    # Input to modify CRDT
    async def on_input(e):
        text.clear()
        text += e.value
        app.storage.tab['content'] = str(text)
        # In real implementation, broadcast update

    input_field = ui.input(
        'Edit text',
        value=str(text),
        on_change=on_input
    )

    # Sync initial state
    app.storage.tab['content'] = str(text)

    # Observe changes from other clients
    def on_update(event):
        app.storage.tab['content'] = str(text)
        input_field.value = str(text)

    doc.observe(on_update)

ui.run()
```

## Sync Protocol Summary

1. **Initial sync**: New client requests full state via `doc.get_update()`
2. **Continuous sync**: Observe changes, send `event.update` bytes over WebSocket
3. **Receive updates**: Apply incoming bytes with `doc.apply_update(update)`
4. **Conflict resolution**: Automatic - CRDTs merge consistently

## Key Points

- Updates are binary (`bytes`) - efficient for network
- State vectors enable differential sync (bandwidth optimization)
- Observers fire after each transaction
- Use transaction origin to prevent echo loops
- pycrdt handles conflict resolution automatically
