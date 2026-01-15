# Spike 1: pycrdt + NiceGUI WebSocket Sync

## Objective
Validate that pycrdt CRDT documents can sync in real-time over NiceGUI WebSockets.

## Acceptance Criteria
- [ ] Create a pycrdt `Doc` with `Text` type
- [ ] Two browser tabs connected to same NiceGUI server
- [ ] Type in one tab, see update appear in the other
- [ ] Updates sync within <100ms

## Implementation Plan

### 1. Create Feature Branch
```bash
git checkout -b spike/pycrdt-nicegui-sync
```

### 2. Write Failing Tests First (TDD)

Create `tests/integration/test_crdt_sync.py`:
- Test: pycrdt Doc can be created with Text type
- Test: Two Doc instances can sync via update/apply_update
- Test: Observer callback fires on changes

Create `tests/e2e/test_two_tab_sync.py` (Playwright):

```python
from playwright.sync_api import Page, expect

def test_two_tab_sync(page: Page, new_context):
    """Two users see real-time sync of text changes."""
    # User 1
    page.goto("http://localhost:8080/spike1")

    # User 2 in separate browser context
    context2 = new_context()
    page2 = context2.new_page()
    page2.goto("http://localhost:8080/spike1")

    # User 1 types
    page.get_by_label("Edit text").fill("Hello from user 1")

    # User 2 sees the update (100ms timeout for sync requirement)
    expect(page2.get_by_test_id("synced-text")).to_have_text(
        "Hello from user 1",
        timeout=100
    )
```

Tests:
- Two browser contexts connect to same page
- Type in context 1, verify text appears in context 2
- Verify sync happens within 100ms

### 3. Implement CRDT Sync Module

Create `src/promptgrimoire/crdt/sync.py`:

```python
from pycrdt import Doc, Text, TransactionEvent

class SharedDocument:
    """Manages a pycrdt Doc with connected clients."""

    def __init__(self):
        self.doc = Doc()
        self.doc["text"] = self.text = Text()
        self.clients: dict[str, Any] = {}
        self.doc.observe(self._on_update)

    def get_full_state(self) -> bytes:
        """Get full document state for new clients."""
        return self.doc.get_update()

    def apply_remote_update(self, update: bytes, origin_client_id: str):
        """Apply update from a client."""
        self.doc.apply_update(update)

    def _on_update(self, event: TransactionEvent):
        """Broadcast update to all clients."""
        # Will call registered broadcast callback
        pass
```

### 4. Implement NiceGUI Page

Create `src/promptgrimoire/pages/sync_demo.py`:

```python
from nicegui import app, ui
from promptgrimoire.crdt.sync import SharedDocument

# Server-side shared document
shared_doc = SharedDocument()
connected_clients: dict[str, Any] = {}

@ui.page('/spike1')
async def sync_demo():
    await ui.context.client.connected()
    client_id = str(id(ui.context.client))

    # Register client
    connected_clients[client_id] = ui.context.client

    # Send initial state
    initial_state = shared_doc.get_full_state()
    # ... send to client via run_javascript

    # Text display
    label = ui.label(str(shared_doc.text))

    # Input field
    async def on_input(e):
        shared_doc.text.clear()
        shared_doc.text += e.value
        # Broadcast to other clients

    ui.input('Edit text', on_change=on_input)

    # Cleanup on disconnect
    async def cleanup():
        connected_clients.pop(client_id, None)

    ui.context.client.on_disconnect(cleanup)
```

### 5. Wire Up Broadcasting

The key challenge: When one client changes the Doc, broadcast the update bytes to all other connected clients via NiceGUI's WebSocket.

Pattern:
1. Client types → `on_change` fires → modify `shared_doc.text`
2. `doc.observe()` callback fires with `event.update` bytes
3. For each other client, call `ui.run_javascript()` to update their UI

### 6. Update Main Entry Point

Modify `src/promptgrimoire/__init__.py` to import and run NiceGUI app.

## File Structure After Implementation

```
src/promptgrimoire/
├── __init__.py          # Modified: add ui.run()
├── crdt/
│   ├── __init__.py
│   └── sync.py          # SharedDocument class
└── pages/
    ├── __init__.py
    └── sync_demo.py     # /spike1 page

tests/
├── integration/
│   └── test_crdt_sync.py
└── e2e/
    └── test_two_tab_sync.py
```

## Verification

1. **Manual test**:
   - Run `uv run python -m promptgrimoire`
   - Open http://localhost:8080/spike1 in two tabs
   - Type in one tab, verify other updates

2. **Integration tests**:
   - `uv run pytest tests/integration/test_crdt_sync.py -v`

3. **E2E tests**:
   - `uv run pytest tests/e2e/test_two_tab_sync.py -v`

## Key Reference Docs

- [pycrdt Usage](docs/pycrdt/usage.md) - Doc, Text, transactions, observers
- [pycrdt WebSocket Sync](docs/pycrdt/websocket-sync.md) - Sync patterns, differential sync
- [NiceGUI Real-Time](docs/nicegui/realtime.md) - WebSocket, on_connect/disconnect
- [NiceGUI UI Patterns](docs/nicegui/ui-patterns.md) - timer, refreshable, run_javascript

## Technical Notes

- pycrdt updates are binary (`bytes`) - efficient for network
- Use `doc.get_update()` for full state, `doc.get_update(state_vector)` for diff
- NiceGUI's `app.on_connect`/`app.on_disconnect` for client tracking
- `ui.run_javascript()` to push updates to client browsers
- Updates are commutative/associative/idempotent - safe for concurrent edits
