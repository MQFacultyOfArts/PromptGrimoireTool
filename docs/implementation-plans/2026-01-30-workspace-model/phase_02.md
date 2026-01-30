# Workspace Model Implementation Plan - Phase 2: CRDT Integration

**Goal:** CRDT persistence works with Workspace model while maintaining backward compatibility with old system.

**Architecture:** Additive changes to PersistenceManager and AnnotationDocumentRegistry. New workspace-aware methods coexist with old case_id-based methods. `document_id` added as optional parameter to `add_highlight()`.

**Tech Stack:** pycrdt, SQLModel, PostgreSQL

**Scope:** 5 phases from original design (this is phase 2 of 5)

**Codebase verified:** 2026-01-31

**Design document:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/93-workspace-model/docs/design-plans/2026-01-30-workspace-model.md`

---

## UAT: Falsifiable Statement

> CRDT state can be persisted to Workspace via `workspace_id` (new system) OR `case_id` (old system), and loaded back with identical results. The old `/demo/live-annotation` route continues to work unchanged.

**How to verify:**
1. Create workspace, add highlight with `document_id`, save via workspace-aware persistence
2. Load from Workspace, verify highlight has `document_id` preserved
3. Use old `/demo/live-annotation` - verify it still works (no regressions)

---

## Key Design Decision: Additive Changes

Phase 4 requires both old and new routes to work simultaneously. Therefore:

- **OLD** `mark_dirty(doc_id)` → saves to `AnnotationDocumentState` (unchanged)
- **NEW** `mark_dirty_workspace(workspace_id)` → saves to `Workspace.crdt_state`

- **OLD** `get_or_create_with_persistence(doc_id)` → loads from `AnnotationDocumentState` (unchanged)
- **NEW** `get_or_create_for_workspace(workspace_id)` → loads from `Workspace.crdt_state`

- **OLD** `add_highlight(..., document_id=None)` → works as before
- **NEW** `add_highlight(..., document_id="uuid")` → stores document_id in highlight

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
## Task 1: Add document_id parameter to add_highlight()

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add_highlight method)
- Create: `tests/unit/test_highlight_document_id.py`

**Step 1: Write the failing test**

Create `tests/unit/test_highlight_document_id.py`:

```python
"""Tests for document_id in highlight data."""

from __future__ import annotations


class TestHighlightDocumentId:
    """Tests for document_id field in highlights."""

    def test_add_highlight_without_document_id_works(self) -> None:
        """Backward compatibility: highlight without document_id works."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Test text",
            author="Author",
        )

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        # document_id should be None when not provided
        assert highlight.get("document_id") is None

    def test_add_highlight_with_document_id(self) -> None:
        """Highlight stores document_id when provided."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Test text",
            author="Author",
            document_id="workspace-doc-uuid-123",
        )

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        assert highlight.get("document_id") == "workspace-doc-uuid-123"

    def test_document_id_survives_crdt_roundtrip(self) -> None:
        """document_id preserved through CRDT state transfer."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        # Create doc with document_id
        doc1 = AnnotationDocument("test-doc-1")
        hl_id = doc1.add_highlight(
            start_word=10,
            end_word=20,
            tag="citation",
            text="Citation text",
            author="Author",
            document_id="my-document-id",
        )

        # Transfer state to another doc
        state_bytes = doc1.get_full_state()
        doc2 = AnnotationDocument("test-doc-2")
        doc2.apply_update(state_bytes)

        # Verify document_id preserved
        highlight = doc2.get_highlight(hl_id)
        assert highlight is not None
        assert highlight.get("document_id") == "my-document-id"

    def test_get_all_highlights_includes_document_id(self) -> None:
        """get_all_highlights returns document_id field."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-doc")
        doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Text 1",
            author="Author",
            document_id="doc-1",
        )
        doc.add_highlight(
            start_word=10,
            end_word=15,
            tag="citation",
            text="Text 2",
            author="Author",
            document_id="doc-2",
        )

        highlights = doc.get_all_highlights()
        assert len(highlights) == 2
        # Sorted by start_word
        assert highlights[0]["document_id"] == "doc-1"
        assert highlights[1]["document_id"] == "doc-2"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_highlight_document_id.py -v`
Expected: FAIL - `add_highlight()` doesn't accept `document_id` parameter

**Step 3: Write minimal implementation**

Modify `src/promptgrimoire/crdt/annotation_doc.py`, update the `add_highlight` method signature and body.

**Current signature (around line 210):**
```python
def add_highlight(
    self,
    start_word: int,
    end_word: int,
    tag: str,
    text: str,
    author: str,
    para_ref: str = "",
    origin_client_id: str | None = None,
) -> str:
```

**New signature:**
```python
def add_highlight(
    self,
    start_word: int,
    end_word: int,
    tag: str,
    text: str,
    author: str,
    para_ref: str = "",
    origin_client_id: str | None = None,
    document_id: str | None = None,
) -> str:
```

**Update the highlight_data dict (around line 239):**

```python
highlight_data = {
    "id": highlight_id,
    "document_id": document_id,  # NEW - can be None for backward compat
    "start_word": start_word,
    "end_word": end_word,
    "tag": tag,
    "text": text,
    "author": author,
    "para_ref": para_ref,
    "created_at": datetime.now(UTC).isoformat(),
    "comments": [],
}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_highlight_document_id.py -v`
Expected: PASS

**Step 5: Verify old tests still pass**

Run: `uv run pytest tests/unit/test_annotation_document.py -v` (if exists)
Expected: PASS - backward compatibility maintained

**Step 6: Commit**

```bash
git add src/promptgrimoire/crdt/annotation_doc.py tests/unit/test_highlight_document_id.py
git commit -m "feat(crdt): add document_id parameter to add_highlight

- Optional document_id parameter for workspace-based highlights
- Backward compatible: None when not provided
- Preserved through CRDT state transfer"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Add get_highlights_for_document() helper

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py`
- Modify: `tests/unit/test_highlight_document_id.py`

**Purpose:** When workspace has multiple documents, need to filter highlights by document_id.

**Step 1: Write the failing test**

Add to `tests/unit/test_highlight_document_id.py`:

```python
class TestGetHighlightsForDocument:
    """Tests for filtering highlights by document_id."""

    def test_get_highlights_for_specific_document(self) -> None:
        """Returns only highlights for specified document_id."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-workspace")

        # Add highlights for different documents
        doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="Doc A highlight 1", author="Author",
            document_id="doc-a",
        )
        doc.add_highlight(
            start_word=10, end_word=15, tag="citation",
            text="Doc B highlight", author="Author",
            document_id="doc-b",
        )
        doc.add_highlight(
            start_word=20, end_word=25, tag="issue",
            text="Doc A highlight 2", author="Author",
            document_id="doc-a",
        )

        # Get highlights for doc-a only
        doc_a_highlights = doc.get_highlights_for_document("doc-a")

        assert len(doc_a_highlights) == 2
        assert all(h["document_id"] == "doc-a" for h in doc_a_highlights)
        # Should be sorted by start_word
        assert doc_a_highlights[0]["start_word"] == 0
        assert doc_a_highlights[1]["start_word"] == 20

    def test_get_highlights_for_unknown_document_returns_empty(self) -> None:
        """Returns empty list for document with no highlights."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-workspace")
        doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="Some highlight", author="Author",
            document_id="doc-a",
        )

        highlights = doc.get_highlights_for_document("doc-nonexistent")

        assert highlights == []

    def test_get_highlights_for_document_excludes_none(self) -> None:
        """Highlights without document_id are NOT returned."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-workspace")

        # Highlight without document_id (old style)
        doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="Old style", author="Author",
        )
        # Highlight with document_id
        doc.add_highlight(
            start_word=10, end_word=15, tag="citation",
            text="New style", author="Author",
            document_id="doc-a",
        )

        highlights = doc.get_highlights_for_document("doc-a")

        assert len(highlights) == 1
        assert highlights[0]["document_id"] == "doc-a"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_highlight_document_id.py::TestGetHighlightsForDocument -v`
Expected: FAIL - `get_highlights_for_document()` doesn't exist

**Step 3: Write minimal implementation**

Add to `src/promptgrimoire/crdt/annotation_doc.py`, after `get_all_highlights()`:

```python
def get_highlights_for_document(self, document_id: str) -> list[dict[str, Any]]:
    """Get all highlights for a specific document.

    Args:
        document_id: The document UUID to filter by.

    Returns:
        List of highlight data dicts for that document, sorted by start_word.
    """
    highlights = [
        h for h in self.highlights.values()
        if h.get("document_id") == document_id
    ]
    return sorted(highlights, key=lambda h: h.get("start_word", 0))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_highlight_document_id.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/crdt/annotation_doc.py tests/unit/test_highlight_document_id.py
git commit -m "feat(crdt): add get_highlights_for_document filter

- Filter highlights by document_id
- Returns sorted by start_word
- Returns empty list for unknown document"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
## Task 3: Add workspace-aware persistence methods to PersistenceManager

**Files:**
- Modify: `src/promptgrimoire/crdt/persistence.py`
- Create: `tests/integration/test_workspace_persistence.py`

**Step 1: Write the failing test**

Create `tests/integration/test_workspace_persistence.py`:

```python
"""Tests for workspace-aware CRDT persistence.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set - skipping database integration tests",
    ),
    pytest.mark.xdist_group("db_integration"),
]


class TestWorkspacePersistence:
    """Tests for workspace-aware persistence."""

    @pytest.mark.asyncio
    async def test_mark_dirty_workspace_schedules_save(self) -> None:
        """mark_dirty_workspace schedules save to Workspace."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        # Setup
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        # Create document and register
        doc = AnnotationDocument(f"ws-{workspace.id}")
        doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="Test", author="Author",
            document_id=str(uuid4()),
        )

        pm = get_persistence_manager()
        pm.register_document(doc)

        # Mark dirty with workspace_id
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Author")

        # Force persist (don't wait for debounce)
        await pm.force_persist_workspace(workspace.id)

        # Verify saved to Workspace
        loaded = await get_workspace(workspace.id)
        assert loaded is not None
        assert loaded.crdt_state is not None
        assert len(loaded.crdt_state) > 0

    @pytest.mark.asyncio
    async def test_workspace_persist_preserves_highlights(self) -> None:
        """Persisted workspace CRDT state preserves all highlights."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        # Create document with highlights
        doc = AnnotationDocument(f"ws-{workspace.id}")
        doc_uuid = str(uuid4())
        hl1_id = doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="First", author="Author",
            document_id=doc_uuid,
        )
        hl2_id = doc.add_highlight(
            start_word=10, end_word=15, tag="citation",
            text="Second", author="Author",
            document_id=doc_uuid,
        )

        pm = get_persistence_manager()
        pm.register_document(doc)
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Author")
        await pm.force_persist_workspace(workspace.id)

        # Load and verify
        loaded_workspace = await get_workspace(workspace.id)
        loaded_doc = AnnotationDocument("loaded")
        loaded_doc.apply_update(loaded_workspace.crdt_state)

        highlights = loaded_doc.get_all_highlights()
        assert len(highlights) == 2
        assert any(h["id"] == hl1_id for h in highlights)
        assert any(h["id"] == hl2_id for h in highlights)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_workspace_persistence.py -v`
Expected: FAIL - `mark_dirty_workspace()` doesn't exist

**Step 3: Write minimal implementation**

Modify `src/promptgrimoire/crdt/persistence.py`:

Add new instance variables to `__init__`:

```python
def __init__(self, debounce_seconds: float = 5.0) -> None:
    # ... existing code ...

    # Workspace-based persistence (new)
    self._workspace_dirty: dict[UUID, str] = {}  # workspace_id -> doc_id
    self._workspace_pending_saves: dict[UUID, asyncio.Task[None]] = {}
    self._workspace_last_editors: dict[UUID, str | None] = {}
```

Add imports at top (if not already present):

```python
import logging
from uuid import UUID

logger = logging.getLogger(__name__)
```

Add new methods:

```python
def mark_dirty_workspace(
    self,
    workspace_id: UUID,
    doc_id: str,
    last_editor: str | None = None,
) -> None:
    """Mark a workspace's CRDT state as needing persistence.

    Args:
        workspace_id: The workspace UUID.
        doc_id: The document ID in the registry.
        last_editor: Display name of last editor.
    """
    self._workspace_dirty[workspace_id] = doc_id
    self._workspace_last_editors[workspace_id] = last_editor
    self._schedule_debounced_workspace_save(workspace_id)

def _schedule_debounced_workspace_save(self, workspace_id: UUID) -> None:
    """Schedule a debounced save for a workspace."""
    # Cancel any existing pending save
    if workspace_id in self._workspace_pending_saves:
        self._workspace_pending_saves[workspace_id].cancel()

    # Schedule new save
    task = asyncio.create_task(self._debounced_workspace_save(workspace_id))
    self._workspace_pending_saves[workspace_id] = task

async def _debounced_workspace_save(self, workspace_id: UUID) -> None:
    """Wait for debounce period then persist workspace."""
    try:
        await asyncio.sleep(self.debounce_seconds)
        await self._persist_workspace(workspace_id)
    except asyncio.CancelledError:
        pass  # Save was superseded by a newer one

async def _persist_workspace(self, workspace_id: UUID) -> None:
    """Persist CRDT state to Workspace table."""
    doc_id = self._workspace_dirty.get(workspace_id)
    if doc_id is None:
        return

    doc = self._doc_registry.get(doc_id)
    if doc is None:
        logger.warning("Document %s not found for workspace %s", doc_id, workspace_id)
        return

    try:
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        crdt_state = doc.get_full_state()
        success = await save_workspace_crdt_state(workspace_id, crdt_state)

        if success:
            self._workspace_dirty.pop(workspace_id, None)
            logger.info("Persisted workspace %s", workspace_id)
        else:
            logger.warning("Workspace %s not found for persistence", workspace_id)

    except Exception:
        logger.exception("Failed to persist workspace %s", workspace_id)

async def force_persist_workspace(self, workspace_id: UUID) -> None:
    """Immediately persist a workspace's CRDT state.

    Args:
        workspace_id: The workspace UUID.
    """
    # Cancel any pending debounced save
    if workspace_id in self._workspace_pending_saves:
        self._workspace_pending_saves[workspace_id].cancel()
        del self._workspace_pending_saves[workspace_id]

    await self._persist_workspace(workspace_id)

async def persist_all_dirty_workspaces(self) -> None:
    """Persist all dirty workspaces immediately."""
    workspace_ids = list(self._workspace_dirty.keys())
    for workspace_id in workspace_ids:
        await self.force_persist_workspace(workspace_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_workspace_persistence.py -v`
Expected: PASS

**Step 5: Verify old persistence still works**

Run: `uv run pytest tests/integration/test_db_async.py -v` (if it tests persistence)
Expected: PASS - old system unchanged

**Step 6: Commit**

```bash
git add src/promptgrimoire/crdt/persistence.py tests/integration/test_workspace_persistence.py
git commit -m "feat(crdt): add workspace-aware persistence methods

- mark_dirty_workspace(workspace_id, doc_id, last_editor)
- force_persist_workspace(workspace_id)
- persist_all_dirty_workspaces()
- Old case_id-based methods unchanged (backward compat)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: Add workspace-aware loading to AnnotationDocumentRegistry

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (AnnotationDocumentRegistry class)
- Modify: `tests/integration/test_workspace_persistence.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_workspace_persistence.py`:

```python
class TestWorkspaceLoading:
    """Tests for loading documents from Workspace."""

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_loads_existing(self) -> None:
        """Loads existing CRDT state from Workspace."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            AnnotationDocumentRegistry,
        )
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            save_workspace_crdt_state,
        )

        # Setup: create workspace with persisted CRDT state
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        # Create and save initial state
        initial_doc = AnnotationDocument("initial")
        doc_uuid = str(uuid4())
        hl_id = initial_doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="Persisted highlight", author="Author",
            document_id=doc_uuid,
        )
        await save_workspace_crdt_state(workspace.id, initial_doc.get_full_state())

        # Load via registry
        registry = AnnotationDocumentRegistry()
        loaded_doc = await registry.get_or_create_for_workspace(workspace.id)

        # Verify loaded
        assert loaded_doc is not None
        highlights = loaded_doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["id"] == hl_id
        assert highlights[0]["document_id"] == doc_uuid

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_creates_empty_if_no_state(self) -> None:
        """Creates empty document if workspace has no CRDT state."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        assert doc is not None
        assert doc.get_all_highlights() == []

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_caches_document(self) -> None:
        """Second call returns cached document."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        registry = AnnotationDocumentRegistry()
        doc1 = await registry.get_or_create_for_workspace(workspace.id)
        doc2 = await registry.get_or_create_for_workspace(workspace.id)

        assert doc1 is doc2  # Same instance

    @pytest.mark.asyncio
    async def test_get_or_create_for_workspace_registers_with_persistence(self) -> None:
        """Loaded document is registered with PersistenceManager."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        pm = get_persistence_manager()
        # Doc should be registered
        assert pm._doc_registry.get(doc.doc_id) is doc
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_workspace_persistence.py::TestWorkspaceLoading -v`
Expected: FAIL - `get_or_create_for_workspace()` doesn't exist

**Step 3: Write minimal implementation**

Add to `AnnotationDocumentRegistry` class in `src/promptgrimoire/crdt/annotation_doc.py`:

First add import at top:
```python
from uuid import UUID
```

Then add method to the class:

```python
async def get_or_create_for_workspace(self, workspace_id: UUID) -> AnnotationDocument:
    """Get existing document for workspace, load from DB, or create new.

    This is the workspace-aware alternative to get_or_create_with_persistence().
    Loads CRDT state from Workspace.crdt_state instead of AnnotationDocumentState.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        The AnnotationDocument instance, restored from DB if available.
    """
    # Use workspace_id as doc_id key for caching
    doc_id = f"ws-{workspace_id}"

    if doc_id in self._documents:
        return self._documents[doc_id]

    # Try to load from Workspace
    from promptgrimoire.crdt.persistence import get_persistence_manager
    from promptgrimoire.db.workspaces import get_workspace

    doc = AnnotationDocument(doc_id)

    try:
        workspace = await get_workspace(workspace_id)
        if workspace and workspace.crdt_state:
            doc.apply_update(workspace.crdt_state)
            logger.info("Loaded workspace %s from database", workspace_id)
    except Exception:
        logger.exception("Failed to load workspace %s from database", workspace_id)

    self._documents[doc_id] = doc

    # Register with persistence manager
    get_persistence_manager().register_document(doc)

    return doc
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_workspace_persistence.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/crdt/annotation_doc.py tests/integration/test_workspace_persistence.py
git commit -m "feat(crdt): add workspace-aware document loading

- get_or_create_for_workspace(workspace_id) loads from Workspace.crdt_state
- Caches document with 'ws-{workspace_id}' key
- Registers with PersistenceManager for save callbacks
- Old get_or_create_with_persistence() unchanged"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
## Task 5: Integration test for full workspace CRDT round-trip

**Files:**
- Modify: `tests/integration/test_workspace_persistence.py`

**Purpose:** End-to-end test that workspace-based CRDT persistence works as expected.

**Step 1: Write the integration test**

Add to `tests/integration/test_workspace_persistence.py`:

```python
class TestWorkspaceCRDTRoundTrip:
    """Full round-trip tests for workspace CRDT persistence."""

    @pytest.mark.asyncio
    async def test_full_workflow_create_annotate_persist_load(self) -> None:
        """Complete workflow: create workspace, annotate, persist, reload."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        # 1. Create workspace
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)
        workspace_doc_id = str(uuid4())  # Simulated WorkspaceDocument ID

        # 2. Get document for workspace
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        # 3. Add annotations
        hl1 = doc.add_highlight(
            start_word=0, end_word=10, tag="issue",
            text="The main legal issue here",
            author="Test Author",
            para_ref="[1]",
            document_id=workspace_doc_id,
        )
        hl2 = doc.add_highlight(
            start_word=20, end_word=30, tag="citation",
            text="Smith v Jones [2024]",
            author="Test Author",
            para_ref="[2]",
            document_id=workspace_doc_id,
        )
        doc.add_comment(hl1, author="Reviewer", text="Good catch!")

        # 4. Persist via workspace-aware method
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Test Author")
        await pm.force_persist_workspace(workspace.id)

        # 5. Clear registry to force reload
        registry.clear_all()

        # 6. Reload from database
        reloaded_doc = await registry.get_or_create_for_workspace(workspace.id)

        # 7. Verify all data survived
        highlights = reloaded_doc.get_all_highlights()
        assert len(highlights) == 2

        # Check highlight details
        hl1_loaded = reloaded_doc.get_highlight(hl1)
        assert hl1_loaded is not None
        assert hl1_loaded["tag"] == "issue"
        assert hl1_loaded["document_id"] == workspace_doc_id
        assert len(hl1_loaded.get("comments", [])) == 1
        assert hl1_loaded["comments"][0]["text"] == "Good catch!"

        hl2_loaded = reloaded_doc.get_highlight(hl2)
        assert hl2_loaded is not None
        assert hl2_loaded["tag"] == "citation"
        assert hl2_loaded["document_id"] == workspace_doc_id

    @pytest.mark.asyncio
    async def test_filter_highlights_by_document_after_reload(self) -> None:
        """Can filter reloaded highlights by document_id."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc_a_id = str(uuid4())
        doc_b_id = str(uuid4())

        # Create highlights for two different documents
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace.id)

        doc.add_highlight(
            start_word=0, end_word=5, tag="issue",
            text="Doc A hl 1", author="Author",
            document_id=doc_a_id,
        )
        doc.add_highlight(
            start_word=10, end_word=15, tag="citation",
            text="Doc B hl 1", author="Author",
            document_id=doc_b_id,
        )
        doc.add_highlight(
            start_word=20, end_word=25, tag="issue",
            text="Doc A hl 2", author="Author",
            document_id=doc_a_id,
        )

        # Persist and reload
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(workspace.id, doc.doc_id, last_editor="Author")
        await pm.force_persist_workspace(workspace.id)
        registry.clear_all()
        reloaded = await registry.get_or_create_for_workspace(workspace.id)

        # Filter by document
        doc_a_highlights = reloaded.get_highlights_for_document(doc_a_id)
        doc_b_highlights = reloaded.get_highlights_for_document(doc_b_id)

        assert len(doc_a_highlights) == 2
        assert len(doc_b_highlights) == 1
        assert all(h["document_id"] == doc_a_id for h in doc_a_highlights)
        assert all(h["document_id"] == doc_b_id for h in doc_b_highlights)


class TestBackwardCompatibility:
    """Tests that old case_id-based system still works."""

    @pytest.mark.asyncio
    async def test_old_persistence_still_works(self) -> None:
        """Old mark_dirty(case_id) -> save_state() path unchanged."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            AnnotationDocumentRegistry,
        )
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db.annotation_state import get_state_by_case_id

        case_id = f"compat-test-{uuid4().hex[:8]}"

        # Use old API
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_with_persistence(case_id)

        doc.add_highlight(
            start_word=0, end_word=5, tag="test",
            text="Old style", author="Author",
            # No document_id - old style
        )

        pm = get_persistence_manager()
        pm.mark_dirty(case_id, "Author")
        await pm.force_persist(case_id)

        # Verify saved to AnnotationDocumentState
        state = await get_state_by_case_id(case_id)
        assert state is not None
        assert state.crdt_state is not None
        assert len(state.crdt_state) > 0
```

**Step 2: Run all Phase 2 integration tests**

Run: `uv run pytest tests/integration/test_workspace_persistence.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_workspace_persistence.py
git commit -m "test: add workspace CRDT round-trip integration tests

- Full workflow: create, annotate, persist, reload
- Filter highlights by document_id after reload
- Backward compatibility: old case_id system unchanged"
```
<!-- END_TASK_5 -->

---

## Phase 2 Verification

Run all Phase 2 tests:

```bash
uv run pytest tests/unit/test_highlight_document_id.py tests/integration/test_workspace_persistence.py -v
```

Expected: All tests pass

Also verify Phase 1 tests still pass (no regressions):

```bash
uv run pytest tests/unit/test_workspace*.py tests/integration/test_workspace_crud.py -v
```

---

## UAT Checklist

- [ ] `document_id` parameter works in `add_highlight()` (Task 1 tests pass)
- [ ] `get_highlights_for_document()` filters correctly (Task 2 tests pass)
- [ ] Workspace-aware persistence saves to Workspace.crdt_state (Task 3 tests pass)
- [ ] Workspace-aware loading works from Workspace.crdt_state (Task 4 tests pass)
- [ ] Full round-trip preserves all data (Task 5 tests pass)
- [ ] Old `/demo/live-annotation` still works (backward compatibility test passes)

**If all tests pass:** Phase 2 complete. CRDT persistence works with workspace model. Proceed to Phase 3.

**If backward compatibility fails:** Old system broken. Fix before proceeding.
