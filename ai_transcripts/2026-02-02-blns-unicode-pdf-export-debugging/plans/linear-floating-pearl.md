# CRDT Database Persistence Layer

## Goals

1. Connect the CRDT `AnnotationDocument` with PostgreSQL so highlights survive server restarts
2. Fix live comment sync so comments appear on remote clients immediately when posted

## Current State

- **CRDT layer** ([annotation_doc.py](src/promptgrimoire/crdt/annotation_doc.py)): `AnnotationDocument` manages highlights/comments via pycrdt, stored in `_doc_registry` (in-memory dict)
- **Database layer** ([models.py](src/promptgrimoire/db/models.py)): Has `Highlight` and `HighlightComment` models, plus precedent for CRDT storage (`Conversation.crdt_state: bytes`)
- **Gaps**:
  1. CRDT state is lost on server restart - no persistence mechanism
  2. Comments don't appear on remote clients - `refresh_annotations()` skips existing highlight cards (line 820)

## Design Decisions

1. **Store CRDT state as bytes** (like `Conversation.crdt_state`) - preserves full history, supports differential sync
2. **Debounced writes** (5 seconds) - avoid overwhelming DB during rapid edits
3. **Force persist on last disconnect** - ensure data saved when document goes "cold"
4. **Load from DB on first access** - restore state after restart

## Implementation Steps

### Step 1: Add `AnnotationDocumentState` Model

**File:** [src/promptgrimoire/db/models.py](src/promptgrimoire/db/models.py)

```python
class AnnotationDocumentState(SQLModel, table=True):
    """Persisted CRDT state for annotation documents."""
    __tablename__ = "annotation_document_state"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    case_id: str = Field(unique=True, index=True, max_length=255)
    crdt_state: bytes
    highlight_count: int = Field(default=0)
    last_editor: str | None = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_timestamptz_column())
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_timestamptz_column())
```

### Step 2: Create Alembic Migration

**File:** `alembic/versions/xxxx_add_annotation_document_state.py`

- Create `annotation_document_state` table
- Add unique index on `case_id`

### Step 3: Create Repository Module

**File:** `src/promptgrimoire/db/annotation_state.py` (new)

```python
async def get_state_by_case_id(case_id: str) -> AnnotationDocumentState | None
async def save_state(case_id: str, crdt_state: bytes, highlight_count: int, last_editor: str | None) -> AnnotationDocumentState
```

Uses upsert pattern (update if exists, insert if not).

### Step 4: Create Persistence Manager

**File:** `src/promptgrimoire/crdt/persistence.py` (new)

```python
class PersistenceManager:
    """Manages debounced persistence of CRDT documents."""

    def register_document(doc: AnnotationDocument) -> None
    def mark_dirty(doc_id: str, last_editor: str | None) -> None  # Schedules debounced save
    async def force_persist(doc_id: str) -> None  # Immediate save
    async def persist_all_dirty() -> None  # For shutdown
```

Key mechanics:
- `_pending_saves: dict[str, asyncio.Task]` - debounce timers per document
- `_dirty_docs: set[str]` - tracks unsaved changes
- 5-second debounce via `asyncio.sleep()` + task cancellation on new edits

### Step 5: Extend AnnotationDocument

**File:** [src/promptgrimoire/crdt/annotation_doc.py](src/promptgrimoire/crdt/annotation_doc.py)

Add to `AnnotationDocument`:
- `_persistence_enabled: bool` flag
- `enable_persistence()` method
- Hook in `_on_update()` to call `PersistenceManager.mark_dirty()`

Add to `AnnotationDocumentRegistry`:
- `async def get_or_create_with_persistence(doc_id: str)` - loads from DB if exists

### Step 6: Wire Up App Lifecycle

**File:** [src/promptgrimoire/__init__.py](src/promptgrimoire/__init__.py)

Add shutdown handler inside the `if os.environ.get("DATABASE_URL"):` block:

```python
from promptgrimoire.crdt.persistence import get_persistence_manager

# In existing shutdown function:
async def shutdown() -> None:
    await get_persistence_manager().persist_all_dirty()
    await close_db()
```

### Step 7: Update Live Annotation Demo

**File:** [src/promptgrimoire/pages/live_annotation_demo.py](src/promptgrimoire/pages/live_annotation_demo.py)

Minimal changes:
1. Change `_doc_registry.get_or_create(doc_id)` → `await _doc_registry.get_or_create_with_persistence(doc_id)`
2. Call `ann_doc.enable_persistence()` after getting document
3. In disconnect handler: call `force_persist()` when last client leaves

## Files to Modify

| File | Change |
|------|--------|
| `src/promptgrimoire/db/models.py` | Add `AnnotationDocumentState` model |
| `src/promptgrimoire/db/__init__.py` | Export new model and functions |
| `src/promptgrimoire/crdt/annotation_doc.py` | Add persistence hooks and async loading |
| `src/promptgrimoire/crdt/__init__.py` | Export new functions |
| `src/promptgrimoire/__init__.py` | Add shutdown persistence hook |
| `src/promptgrimoire/pages/live_annotation_demo.py` | Enable persistence + fix comment live refresh |

## New Files

| File | Purpose |
|------|---------|
| `src/promptgrimoire/db/annotation_state.py` | Repository for CRDT state CRUD |
| `src/promptgrimoire/crdt/persistence.py` | Debounced write manager |
| `alembic/versions/xxxx_add_annotation_document_state.py` | Schema migration |
| `tests/unit/test_crdt_persistence.py` | Unit tests for persistence manager |
| `tests/integration/test_crdt_db_integration.py` | Integration tests for round-trip |

## Step 8: Fix Comment Live Refresh (Bug Fix)

**File:** [src/promptgrimoire/pages/live_annotation_demo.py](src/promptgrimoire/pages/live_annotation_demo.py)

The current `refresh_annotations()` (line 806-825) skips highlights that already have cards. When a comment is added remotely, the card exists but doesn't show the new comment.

**Fix:** Use `@ui.refreshable` for the comments section. Each card gets its own refreshable function that can be called to update just the comments without recreating the whole card.

1. **Track refreshable functions per highlight** in `_PageContext`:
   ```python
   self.annotation_cards: dict[str, ui.element] = {}
   self.comment_refreshers: dict[str, Callable] = {}  # NEW: highlight_id -> refresh function
   ```

2. **Create refreshable comments section in `_create_annotation_card()`**:
   ```python
   def _create_annotation_card(...) -> None:
       # ... existing card setup ...

       # Create a refreshable function for this card's comments
       @ui.refreshable
       def comments_section():
           # Get fresh comments from CRDT
           highlight = ctx.ann_doc.get_highlight(highlight_id)
           comments = highlight.get("comments", []) if highlight else []
           _build_card_comments(comments)

       # Store the refresher so we can call it later
       ctx.comment_refreshers[highlight_id] = comments_section.refresh

       with card:
           # ... header, author, text, go-to-button ...
           comments_section()  # Render comments
           _build_card_comment_input(ctx, highlight_id, comments_section.refresh, broadcast_update)
   ```

3. **Update `_build_card_comment_input()` to use the refresher** (no more delete/recreate):
   ```python
   def _build_card_comment_input(
       ctx: _PageContext,
       highlight_id: str,
       refresh_comments: Callable,  # Changed from refresh_annotations
       broadcast_update: Any,
   ) -> None:
       comment_input = ui.input(placeholder="Add comment...").props("dense").classes("w-full")

       async def add_comment(hid: str = highlight_id, inp: ui.input = comment_input) -> None:
           if inp.value.strip():
               ctx.ann_doc.add_comment(hid, ctx.username, inp.value, origin_client_id=ctx.client_id)
               inp.value = ""
               refresh_comments()  # Just refresh comments, not whole card
               await broadcast_update()

       ui.button("Post", on_click=add_comment).props("dense size=sm")
   ```

4. **Update `refresh_annotations()` to refresh existing cards' comments**:
   ```python
   async def refresh_annotations() -> None:
       highlights = ctx.ann_doc.get_all_highlights()
       current_ids = {h.get("id", "") for h in highlights}

       # Remove cards for deleted highlights
       for hid in list(ctx.annotation_cards.keys()):
           if hid not in current_ids:
               ctx.annotation_cards[hid].delete()
               del ctx.annotation_cards[hid]
               ctx.comment_refreshers.pop(hid, None)

       # Create new cards or refresh existing ones
       for h in highlights:
           highlight_id = h.get("id", "")
           if highlight_id in ctx.annotation_cards:
               # Card exists - just refresh comments
               if highlight_id in ctx.comment_refreshers:
                   ctx.comment_refreshers[highlight_id]()
           else:
               # New highlight - create card
               _create_annotation_card(ctx, h, update_highlight_css, broadcast_update, refresh_annotations)
   ```

This approach:
- Never deletes/recreates cards for comment updates
- Uses NiceGUI's `@ui.refreshable` pattern for targeted updates
- Keeps the card structure stable (scroll position, animations preserved)
- Each card independently refreshable

## Verification

1. **Run migration:** `uv run alembic upgrade head`
2. **Run unit tests:** `uv run pytest tests/unit/test_crdt_persistence.py -v`
3. **Run integration tests:** `uv run pytest tests/integration/test_crdt_db_integration.py -v`
4. **Manual E2E test - Persistence:**
   - Start app: `uv run python -m promptgrimoire`
   - Open `/demo/live-annotation`
   - Add highlights
   - Restart server
   - Verify highlights persist
5. **Manual E2E test - Comment sync:**
   - Open `/demo/live-annotation` in two browser tabs
   - Add a highlight in tab 1
   - Add a comment in tab 1
   - Verify comment appears in tab 2 immediately
