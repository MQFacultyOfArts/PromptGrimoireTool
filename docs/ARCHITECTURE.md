# PromptGrimoire Architecture

## Library Integration Patterns

### Data Flow

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (Client)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ NiceGUI UI  │  │ Text Select  │  │ pycrdt (WASM/JS sync)  │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬────────────┘  │
└─────────┼────────────────┼──────────────────────┼───────────────┘
          │ WebSocket      │ JS events            │ CRDT updates
          │                │                      │
┌─────────┼────────────────┼──────────────────────┼───────────────┐
│         ▼                ▼                      ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    NiceGUI Server                        │   │
│  │  - Async event loop                                      │   │
│  │  - WebSocket per client                                  │   │
│  │  - app.on_connect/on_disconnect for presence             │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
│         ┌──────────────────┼──────────────────────┐            │
│         ▼                  ▼                      ▼            │
│  ┌────────────┐    ┌─────────────┐    ┌──────────────────┐    │
│  │   Stytch   │    │   pycrdt    │    │     SQLModel     │    │
│  │  (auth)    │    │   (CRDT)    │    │   (PostgreSQL)   │    │
│  └────────────┘    └─────────────┘    └──────────────────┘    │
│                                                                 │
│                         Python Server                           │
└─────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### 1. NiceGUI (Web Framework)

- Serves the UI
- Manages WebSocket connections to each client
- Handles client lifecycle events
- Provides reactive bindings for UI updates

**Key patterns:**

```python
from nicegui import ui, app

@app.on_connect()
async def on_connect(client):
    # Track connected users for presence
    pass

@app.on_disconnect()
async def on_disconnect(client):
    # Clean up presence
    pass
```

### 2. pycrdt (Real-time Collaboration)

- Maintains CRDT document state per conversation
- Generates binary updates on changes
- Applies remote updates from other clients
- Handles conflict resolution automatically

**Key patterns:**

```python
from pycrdt import Doc, Text

# One Doc per conversation
doc = Doc()
doc["annotations"] = annotations_map

# Observe and broadcast changes
def on_doc_change(event):
    update = event.update
    # Broadcast to other clients via NiceGUI WebSocket
    for client in connected_clients:
        client.send(update)

doc.observe(on_doc_change)
```

### 3. Stytch (Authentication)

**Decision needed: B2C vs B2B**

Option A: **B2C + Custom RBAC**

- Simpler auth flow
- We manage classes/roles in our DB
- More flexibility

```python
# B2C flow
client = stytch.Client(project_id, secret)
await client.magic_links.email.login_or_create_async(email=email, ...)
# Then check our DB for class membership/roles
```

Option B: **B2B (Organizations as Classes)**

- Stytch manages org membership
- Built-in RBAC
- Invitations handled

```python
# B2B flow
await client.organizations.members.create_async(
    organization_id=class_id,
    email_address=email,
    roles=["student"]
)
```

### 4. SQLModel + PostgreSQL (Persistence)

- Store user data, class membership
- Store conversation raw text
- Store CRDT state snapshots (for recovery)
- Index tags for search

**Key patterns:**

```python
from sqlmodel import SQLModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

class Conversation(SQLModel, table=True):
    id: UUID
    crdt_state: bytes  # doc.get_update() snapshot

async def save_crdt_state(session: AsyncSession, conv_id: UUID, doc: Doc):
    conv = await session.get(Conversation, conv_id)
    conv.crdt_state = doc.get_update()
    session.add(conv)
    await session.commit()
```

## Integration Points

### A. NiceGUI ↔ pycrdt (Real-time sync)

Challenge: pycrdt is Python, but selection happens in browser JS.

Solution:

1. Use `ui.run_javascript()` to capture text selection ranges
2. Send selection events to Python via NiceGUI's event system
3. Create annotations in pycrdt Doc
4. Broadcast updates to other clients

```python
# Capture selection in browser
selection_js = """
    const sel = window.getSelection();
    return {
        start: sel.anchorOffset,
        end: sel.focusOffset,
        text: sel.toString()
    };
"""

async def on_selection_complete():
    selection = await ui.run_javascript(selection_js)
    # Create annotation in CRDT
    with doc.transaction():
        annotations.append({
            "start": selection["start"],
            "end": selection["end"],
            "user_id": current_user.id
        })
```

### B. pycrdt ↔ PostgreSQL (Persistence)

Strategy: Periodic snapshots + event sourcing

1. On every CRDT change, optionally log the update
2. Periodically save full state snapshot
3. On load, restore from latest snapshot

```python
# Save snapshot every N changes or M seconds
async def persist_state():
    state = doc.get_update()
    conv.crdt_state = state
    await session.commit()

# Restore on load
async def load_conversation(conv_id: UUID):
    conv = await session.get(Conversation, conv_id)
    doc = Doc()
    if conv.crdt_state:
        doc.apply_update(conv.crdt_state)
    return doc
```

### C. Stytch ↔ SQLModel (Auth + Data)

If B2C: Stytch provides user identity, we store everything else

```python
# After Stytch auth
stytch_user = await client.magic_links.authenticate_async(token)

# Find or create in our DB
user = await session.exec(
    select(User).where(User.email == stytch_user.user.emails[0].email)
).first()

if not user:
    user = User(email=stytch_user.user.emails[0].email)
    session.add(user)
```

## Derisking Spikes

Before full implementation, build minimal proofs:

### Spike 1: pycrdt + NiceGUI WebSocket

- Create Doc with Text
- Two browser tabs
- Type in one, see update in other
- Validates: CRDT sync over NiceGUI WebSocket

### Spike 2: Text Selection → Annotation

- Display static text in NiceGUI
- Click-drag to select
- Capture range via JS
- Create highlight (CSS class)
- Validates: Browser JS ↔ Python bridge

### Spike 3: Stytch Magic Link Flow

- Send magic link
- Handle callback
- Create session
- Validates: Auth flow works with NiceGUI

### Spike 4: SQLModel Async + PostgreSQL

- Define models
- Create tables
- Insert/query async
- Validates: Async DB works

### Spike 5: Full Annotation Flow

- Combine spikes 1-4
- User logs in → sees conversation → selects text → annotation syncs
- Validates: End-to-end integration
