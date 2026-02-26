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

**Decision: B2B** (decided 2026-02-26, see `docs/design-plans/2026-02-26-aaf-oidc-auth-188-189.md`)

B2B is required because Stytch B2C cannot connect to custom OIDC providers. AAF (Australian Access Federation) requires a generic OIDC connection, which is B2B-only. The app uses a single Stytch organisation.

**Login hierarchy:**

| Priority | Method | Audience |
|----------|--------|----------|
| Primary | AAF OIDC (SSO) | All MQ staff + students |
| Backstop | Google OAuth | Students who can't AAF |
| Back-backstop | Magic Link | Edge cases (domain-restricted to MQ) |
| Dev/admin | GitHub OAuth | Developer access |

**Key components:**
- `AuthClientProtocol` — provider-agnostic interface for auth clients
- `AuthResult` — returned by all auth paths, carries `trusted_metadata` from IdP
- `derive_roles_from_metadata()` — maps AAF `eduperson_affiliation` to app roles
- B2C fallback documented in `docs/b2c-fallback.md` if B2B proves unworkable

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

## Database Initialization

### Schema Management: Alembic Only

All database schema changes go through Alembic migrations. Never use `SQLModel.metadata.create_all()` outside of Alembic.

**Why:**

- Migrations capture schema evolution history
- `create_all()` can diverge from migrations
- Production requires controlled schema changes

**Files:**

- `alembic/env.py` - Imports all models, sets `target_metadata = SQLModel.metadata`
- `alembic/versions/*.py` - Individual migrations
- `src/promptgrimoire/db/models.py` - All 6 SQLModel table classes
- `src/promptgrimoire/db/bootstrap.py` - Unified initialization functions

### Startup Sequence

```python
# src/promptgrimoire/__init__.py
@app.on_startup
async def startup():
    await init_db()                      # Create engine
    await verify_schema(get_engine())    # Validate tables exist
```

### Model Registration

SQLModel requires all table classes to be imported before schema operations:

```python
# This import registers all 6 tables with SQLModel.metadata
import promptgrimoire.db.models  # noqa: F401

# Now metadata.tables contains: user, class, conversation,
# highlight, highlight_comment, annotation_document_state
```

### Test Database Setup

Tests use UUID-based isolation for parallel execution:

```text
1. pytest starts
2. db_schema_guard fixture (session-scoped) runs:
   - Sets DATABASE_URL from TEST_DATABASE_URL
   - Runs `alembic upgrade head`
3. Tests run (potentially in parallel with pytest-xdist)
   - Each test uses unique UUIDs for its data
   - No table drops or truncations
4. Session ends, DB remains populated (harmless with UUIDs)
```

### Bootstrap Functions

```python
from promptgrimoire.db import (
    is_db_configured,      # Check if DATABASE_URL is set
    run_alembic_upgrade,   # Run migrations (subprocess)
    verify_schema,         # Validate tables exist (async)
    get_expected_tables,   # Get table names from metadata
)
```

## Derisking Spikes

Before full implementation, build minimal proofs:

### Spike 1: pycrdt + NiceGUI WebSocket

- Create Doc with Text
- Two browser tabs
- Type in one, see update in other
- Validates: CRDT sync over NiceGUI WebSocket

**Reference Docs:**

- [pycrdt Usage Guide](pycrdt/usage.md) - Doc, Text, transactions, observers
- [pycrdt WebSocket Sync](pycrdt/websocket-sync.md) - Sync patterns, NiceGUI integration
- [NiceGUI Real-Time](nicegui/realtime.md) - WebSocket, multi-client, on_connect/on_disconnect
- [NiceGUI UI Patterns](nicegui/ui-patterns.md) - timer (for sync), storage (for client tracking)

### Spike 2: Text Selection → Annotation

- Display static text in NiceGUI
- Click-drag to select
- Capture range via JS
- Create highlight (CSS class)
- Validates: Browser JS ↔ Python bridge

**Reference Docs:**

- [Browser Selection API](browser/selection-api.md) - getSelection(), Range, coordinates
- [NiceGUI UI Patterns](nicegui/ui-patterns.md) - run_javascript, add_css, element.on(), custom events

### Spike 3: Stytch Magic Link Flow

- Send magic link
- Handle callback
- Create session
- Validates: Auth flow works with NiceGUI

**Reference Docs:**

- [Stytch Magic Link Flow](stytch/magic-link-flow.md) - Complete flow with NiceGUI integration
- [Stytch Passkeys](stytch/passkeys.md) - WebAuthn registration/authentication
- [Stytch Python SDK](stytch/python-sdk.md) - Client setup, async methods
- [NiceGUI UI Patterns](nicegui/ui-patterns.md) - @ui.page routing, storage for sessions

### Spike 4: SQLModel Async + PostgreSQL

- Define models
- Create tables
- Insert/query async
- Validates: Async DB works

**Reference Docs:**

- [SQLModel Overview](sqlmodel/overview.md) - Models, relationships, async session factory, NiceGUI integration
- [asyncpg Usage](asyncpg/usage.md) - Connection pools, SQLAlchemy integration
- [Alembic SQLModel Setup](alembic/sqlmodel-setup.md) - Async migrations

### Spike 5: Full Annotation Flow (E2E)

- Combine spikes 1-4
- User logs in → sees conversation → selects text → annotation syncs
- Validates: End-to-end integration

**Reference Docs:**

- All docs from Spikes 1-4
- [Playwright E2E Testing](playwright/e2e-testing.md) - Multi-user testing, locators, assertions
