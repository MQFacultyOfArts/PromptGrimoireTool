# NiceGUI Multi-Client UI Synchronization

> **Project Notes**: Lessons learned from PromptGrimoire Spike 1 implementation.

## The Problem

When one client makes a change, how do you push that update to all other connected clients?

NiceGUI uses WebSockets automatically, but updating a Python variable doesn't automatically push to other clients' browsers.

## The Solution

Store references to each client's UI elements and call `.update()` to force WebSocket push.

### Pattern

```python
from nicegui import ui

# Track connected clients: client_id -> UI elements
_connected_clients: dict[str, tuple[ui.label, ui.input]] = {}

def _broadcast_to_other_clients(origin_client_id: str | None, content: str) -> None:
    """Update UI elements for all clients except the origin."""
    for client_id, (label, input_elem) in _connected_clients.items():
        if client_id != origin_client_id:
            try:
                label.text = content
                input_elem.value = content
                # Force WebSocket push
                label.update()
                input_elem.update()
            except Exception:
                # Client may have disconnected
                pass


@ui.page("/my-page")
async def my_page() -> None:
    await ui.context.client.connected()

    client = ui.context.client
    client_id = str(id(client))

    # Create UI elements
    display_label = ui.label("")

    def on_input_change(e) -> None:
        new_value = e.value or ""
        # Update own display
        display_label.text = new_value
        # Broadcast to others
        _broadcast_to_other_clients(client_id, new_value)

    input_field = ui.input(on_change=on_input_change)

    # Store references for broadcasting
    _connected_clients[client_id] = (display_label, input_field)

    # Cleanup on disconnect
    def on_disconnect() -> None:
        _connected_clients.pop(client_id, None)

    client.on_disconnect(on_disconnect)
```

## Key Points

1. **`await ui.context.client.connected()`** - Wait for WebSocket before accessing client
2. **`str(id(client))`** - Simple unique identifier per connection
3. **`.update()` method** - Forces the element to push its current state over WebSocket
4. **`client.on_disconnect()`** - Clean up when client leaves
5. **Try/except in broadcast** - Clients may disconnect mid-broadcast

## Why `.update()` is Needed

NiceGUI's reactivity works within a single client context. When you modify an element's property (like `label.text = "new"`), it updates for that client. But other clients have their own element instances.

By storing references and calling `.update()`, you're telling NiceGUI: "This element changed, push it to its client's browser now."

## Scaling Considerations

This pattern works for small numbers of concurrent users. For larger scale:

- Consider using NiceGUI's `app.storage` for shared state
- Use proper pub/sub (Redis, etc.) for cross-process sync
- The CRDT approach (see pycrdt docs) handles conflict resolution

## See Also

- [src/promptgrimoire/pages/sync_demo.py](../../src/promptgrimoire/pages/sync_demo.py) - Working implementation
- [realtime.md](realtime.md) - NiceGUI real-time features
