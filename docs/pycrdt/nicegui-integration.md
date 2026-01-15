# pycrdt Integration with NiceGUI

> **Project Notes**: Lessons learned from PromptGrimoire Spike 1 implementation.

## Overview

This documents how we integrated pycrdt CRDTs with NiceGUI's WebSocket-based architecture for real-time collaborative editing.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    NiceGUI Server                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │              SharedDocument                      │   │
│  │  ┌─────────┐                                    │   │
│  │  │ pycrdt  │  doc.observe() ──► broadcast to   │   │
│  │  │  Doc    │                     other clients  │   │
│  │  │ + Text  │                                    │   │
│  │  └─────────┘                                    │   │
│  └─────────────────────────────────────────────────┘   │
│           ▲                           │                 │
│           │ on_change                 │ .update()       │
│           │                           ▼                 │
│  ┌────────┴────────┐         ┌────────────────┐        │
│  │ Client 1 Input  │         │ Client 2 Label │        │
│  │ (WebSocket)     │         │ (WebSocket)    │        │
│  └─────────────────┘         └────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

## The SharedDocument Wrapper

We wrap pycrdt's `Doc` to handle multi-client coordination:

```python
from pycrdt import Doc, Text, TransactionEvent

class SharedDocument:
    """Manages a pycrdt Doc with connected clients."""

    def __init__(self) -> None:
        self.doc = Doc()
        self.doc["text"] = Text()
        self._clients: dict[str, Any] = {}
        self._broadcast_callback = None
        self._current_origin: str | None = None

        # Observer fires on any change
        self.doc.observe(self._on_update)

    @property
    def text(self) -> Text:
        return self.doc["text"]

    def set_text(self, content: str, origin_client_id: str | None = None) -> None:
        """Replace text content, tracking origin for echo prevention."""
        self._current_origin = origin_client_id
        text = self.text
        text.clear()
        if content:
            text += content
        self._current_origin = None

    def _on_update(self, event: TransactionEvent) -> None:
        """Broadcast updates to other clients."""
        if self._broadcast_callback is not None:
            origin = getattr(self, "_current_origin", None)
            self._broadcast_callback(event.update, origin)

    def get_content(self) -> str:
        return str(self.text)
```

## Key Integration Points

### 1. Origin Tracking for Echo Prevention

When Client A makes a change, we don't want to echo it back to Client A. Track the origin:

```python
def set_text(self, content: str, origin_client_id: str | None = None) -> None:
    self._current_origin = origin_client_id  # Set before change
    # ... make changes ...
    self._current_origin = None  # Clear after

def _on_update(self, event: TransactionEvent) -> None:
    origin = self._current_origin
    # Broadcast to all EXCEPT origin
    self._broadcast_callback(event.update, origin)
```

### 2. Module-Level Singleton

For a single shared document across all clients:

```python
# At module level - shared by all page instances
shared_doc = SharedDocument()
```

### 3. NiceGUI Page Integration

```python
@ui.page("/collaborative")
async def collaborative_page() -> None:
    await ui.context.client.connected()
    client_id = str(id(ui.context.client))

    # Register client
    shared_doc.register_client(client_id)

    # Create UI with current content
    label = ui.label(shared_doc.get_content())

    def on_input_change(e) -> None:
        shared_doc.set_text(e.value or "", origin_client_id=client_id)
        label.text = shared_doc.get_content()
        # Broadcast to others...

    input_field = ui.input(value=shared_doc.get_content(), on_change=on_input_change)

    # Cleanup
    ui.context.client.on_disconnect(lambda: shared_doc.unregister_client(client_id))
```

## What We're NOT Using (Yet)

The full pycrdt sync protocol includes:

- **Binary updates** (`doc.get_update()`) - efficient over network
- **State vectors** (`doc.get_state()`) - for differential sync
- **Position-based editing** (`text.insert(pos, str)`) - for cursor-aware edits

Currently we use simple `set_text()` which replaces the whole content. For true collaborative editing with cursor positions, you'd use the position-based operations.

## Performance Characteristics

- **Sync latency**: <100ms in our tests (250ms with CI tolerance)
- **Conflict resolution**: Automatic via CRDT - no data loss
- **Memory**: One Doc instance on server, UI elements per client

## See Also

- [usage.md](usage.md) - pycrdt basics
- [websocket-sync.md](websocket-sync.md) - Binary sync protocol
- [../nicegui/multi-client-sync.md](../nicegui/multi-client-sync.md) - NiceGUI broadcasting
- [../../src/promptgrimoire/crdt/sync.py](../../src/promptgrimoire/crdt/sync.py) - Implementation
