# Plan: Fix Spike 1 Code Review Issues

**Scope:** Address code review findings for CRDT sync (Spike 1) that are currently in main.

---

## Issues to Fix

### CRITICAL - Thread Safety in Origin Tracking (#3)

**Problem:** `_current_origin` instance variable isn't async-safe. Concurrent updates could interleave and lose origin context.

**Files:** [sync.py](src/promptgrimoire/crdt/sync.py)

**Fix:** Replace instance variable with `contextvars.ContextVar`:

```python
from contextvars import ContextVar

_origin_var: ContextVar[str | None] = ContextVar('origin', default=None)
```

Then use token-based set/reset pattern:
```python
def apply_update(self, update: bytes, origin_client_id: str | None = None) -> None:
    token = _origin_var.set(origin_client_id)
    try:
        self.doc.apply_update(update)
    finally:
        _origin_var.reset(token)
```

**Affected methods:**
- `apply_update()` (lines 50-52)
- `set_text()` (lines 61-66)
- `insert_at()` (lines 78-80)
- `delete_range()` (lines 92-94)
- `_on_update()` (line 131 - read from ContextVar instead of instance)

---

### MEDIUM - Hard-coded Port (#8)

**Problem:** Port 8080 is hard-coded in `__init__.py`.

**Files:** [__init__.py](src/promptgrimoire/__init__.py)

**Fix:**
```python
import os

port = int(os.environ.get("PROMPTGRIMOIRE_PORT", "8080"))
ui.run(port=port, reload=False)
```

---

### MEDIUM - Loose Typing for `_clients` (#11)

**Problem:** `dict[str, Any]` doesn't document what client data is expected.

**Files:** [sync.py](src/promptgrimoire/crdt/sync.py)

**Fix:** Add a TypedDict (or keep flexible with documentation):

```python
from typing import TypedDict

class ClientInfo(TypedDict, total=False):
    """Optional metadata for registered clients."""
    label: Label
    input: Input
    connected_at: float
```

However, since the actual client_data varies by use case (sync_demo stores UI elements, other uses might differ), the better fix is to make it generic:

```python
from typing import TypeVar

T = TypeVar('T')

class SharedDocument(Generic[T]):
    def __init__(self) -> None:
        self._clients: dict[str, T] = {}
```

**Decision:** Given spike nature, I'll add documentation comment explaining the `Any` is intentional for flexibility, and note this as future cleanup.

---

### MEDIUM - Singleton Pattern Documentation (#10)

**Problem:** Module-level `shared_doc` singleton doesn't scale to multiple rooms/documents.

**Files:** [sync_demo.py](src/promptgrimoire/pages/sync_demo.py)

**Fix:** Add comment documenting this as a known limitation:
```python
# NOTE: Single shared document for demo purposes.
# Production will need document-per-room pattern (see docs/pycrdt/nicegui-integration.md)
shared_doc = SharedDocument()
```

---

## Implementation Order

1. Fix ContextVar in sync.py (CRITICAL)
2. Add environment variable for port in __init__.py
3. Add documentation comments for typing and singleton
4. Run tests to verify no regressions

---

## Verification

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific CRDT tests
uv run pytest tests/integration/test_crdt_sync.py tests/e2e/test_two_tab_sync.py -v
```

Manual verification:
1. Start server: `uv run python -m promptgrimoire`
2. Open two tabs to `/demo/crdt-sync`
3. Type in both tabs simultaneously - verify sync still works

---

## Files to Modify

1. [src/promptgrimoire/crdt/sync.py](src/promptgrimoire/crdt/sync.py) - ContextVar + typing docs
2. [src/promptgrimoire/__init__.py](src/promptgrimoire/__init__.py) - environment variable port
3. [src/promptgrimoire/pages/sync_demo.py](src/promptgrimoire/pages/sync_demo.py) - singleton documentation

---

## Future Work: Document-per-Conversation Spike

**Not part of this PR** - requires a separate spike to explore:

### Why a Spike?
The singleton pattern works for demo but production needs document isolation per conversation. This involves:
- Routing: `/conversation/{id}` → specific CRDT document
- Persistence: Load/save CRDT state to PostgreSQL
- Auth integration: Only authorized users access a conversation's document
- Lifecycle: When to create/destroy documents, memory management

### Suggested Spike Acceptance Criteria
1. Create a `DocumentRegistry` that manages multiple `SharedDocument` instances
2. Route parameter determines which document a client connects to
3. Two users on `/conversation/A` sync with each other
4. Two users on `/conversation/B` sync with each other
5. Changes in A do not appear in B (isolation verified)
6. Late joiner to existing conversation gets current state

### Dependencies
- Likely blocked by: Persistence spike (need to store/retrieve CRDT state)
- Likely blocked by: Auth spike (need to know who can access what)

### GitHub Issue
Create issue: "Spike: Document-per-conversation CRDT isolation"
