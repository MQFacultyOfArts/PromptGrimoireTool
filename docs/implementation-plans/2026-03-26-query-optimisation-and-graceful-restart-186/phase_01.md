# Query Optimisation and Graceful Restart — Phase 1

**Goal:** Eliminate unnecessary `content` column transfer on page load by introducing `list_document_headers()` with `defer()` and migrating all non-export callers.

**Architecture:** New `list_document_headers()` function in `workspace_documents.py` uses SQLAlchemy `defer(WorkspaceDocument.content)` to exclude the large text column. Four callers switch to headers-only; export paths remain unchanged. `document_container()` uses a two-query pattern: headers for the list, `get_document()` for the single doc that needs content.

**Tech Stack:** SQLAlchemy `defer()` (new to this project), SQLModel, PostgreSQL

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-03-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### query-optimisation-and-graceful-restart-186.AC1: Query optimisation
- **query-optimisation-and-graceful-restart-186.AC1.1 Success:** `list_document_headers()` returns documents with all metadata columns; no `content` column transferred
- **query-optimisation-and-graceful-restart-186.AC1.2 Success:** Page load callers (`workspace.py`, `tab_bar.py` ×2) use `list_document_headers()`
- **query-optimisation-and-graceful-restart-186.AC1.3 Failure:** Accessing `.content` on a headers-only object raises `DetachedInstanceError`
- **query-optimisation-and-graceful-restart-186.AC1.4 Success:** Export callers (`pdf_export.py`, `cli/export.py`) still receive full `content`

---

## Implementation Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create `list_document_headers()` in workspace_documents.py

**Verifies:** query-optimisation-and-graceful-restart-186.AC1.1, query-optimisation-and-graceful-restart-186.AC1.3

**Files:**
- Modify: `src/promptgrimoire/db/workspace_documents.py:96` (add new function before `list_documents()`)

**Implementation:**

Add `list_document_headers()` directly after the existing `get_document()` function (line ~93) and before `list_documents()` (line ~96). The function is identical to `list_documents()` but adds `.options(defer(WorkspaceDocument.content))`:

```python
from sqlalchemy.orm import defer

async def list_document_headers(workspace_id: UUID) -> list[WorkspaceDocument]:
    """List document metadata without content, ordered by order_index.

    Returns WorkspaceDocument objects with the ``content`` column deferred.
    Accessing ``.content`` on these objects raises ``DetachedInstanceError``
    because the session is closed before return.

    Use ``get_document()`` to fetch a single document with full content,
    or ``list_documents()`` for export paths that need all content.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument)
            .where(WorkspaceDocument.workspace_id == workspace_id)
            .options(defer(WorkspaceDocument.content))
            .order_by("order_index")
        )
        return list(result.all())
```

Add `list_document_headers` to the module's exports if there's an `__all__`.

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors from the new function

**Commit:** `feat: add list_document_headers() with deferred content column (#186, #432)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Migrate callers to `list_document_headers()`

**Verifies:** query-optimisation-and-graceful-restart-186.AC1.2, query-optimisation-and-graceful-restart-186.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:24,248`
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py:19,648`
- Modify: `src/promptgrimoire/pages/annotation/document_management.py:33,181`
- NO changes to: `src/promptgrimoire/cli/export.py` (export paths keep `list_documents()`)
- NO changes to: `src/promptgrimoire/pages/annotation/pdf_export.py` (export path)

**Implementation:**

**workspace.py** — Line 24: add `list_document_headers` to import from `workspace_documents`. Line 248: change `list_documents(workspace_id)` to `list_document_headers(workspace_id)`. The header only uses `first_doc.auto_number_paragraphs` — no content access.

**tab_bar.py** — Line 19: add `list_document_headers` to import, also ensure `get_document` is imported. Line 648 in `document_container()`: change to two-query pattern:

```python
docs = await list_document_headers(workspace_id)
has_documents.clear()
has_documents.append(bool(docs))
logger.debug("[RENDER] documents loaded: count=%d", len(docs))

if docs:
    first_doc = await get_document(docs[0].id)
    assert first_doc is not None, f"Document {docs[0].id} vanished between queries"
    await render_document_container(
        state,
        first_doc,
        crdt_doc,
        on_add_tag=on_add_tag if can_create_tags else None,
        on_manage_tags=on_manage_tags,
        footer=footer,
    )
```

**document_management.py** — Line 33: add `list_document_headers` to import. Line 181: change `list_documents(state.workspace_id)` to `list_document_headers(state.workspace_id)`.

Also update `_document_display_name()` (line 48) to handle deferred content gracefully. Currently the function checks `doc.title` first (safe), then falls back to `doc.content` (raises `DetachedInstanceError` on headers-only objects). Add a try/except:

```python
def _document_display_name(doc: WorkspaceDocument) -> str:
    """Return a display name for a document.

    Uses the title if set, otherwise extracts the first 50 characters
    of plain text from the HTML content. Returns "Untitled" when content
    is deferred (headers-only query) or empty.
    """
    if doc.title:
        return doc.title
    try:
        if doc.content:
            text = LexborHTMLParser(doc.content).text(separator=" ").strip()
            if text:
                preview = text[:_PREVIEW_MAX_CHARS]
                if len(text) > _PREVIEW_MAX_CHARS:
                    preview += "..."
                return preview
    except DetachedInstanceError:
        pass
    return "Untitled"
```

Add `from sqlalchemy.exc import DetachedInstanceError` to the imports.

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors

Run: `uv run grimoire test all`
Expected: All existing tests pass (callers changed but behavior preserved)

**Commit:** `refactor: migrate page-load callers to list_document_headers() (#186, #432)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Integration tests for `list_document_headers()`

**Verifies:** query-optimisation-and-graceful-restart-186.AC1.1, query-optimisation-and-graceful-restart-186.AC1.3, query-optimisation-and-graceful-restart-186.AC1.4

**Files:**
- Create: `tests/integration/test_document_headers.py`

**Testing:**

Tests must verify each AC listed above against a real database:

- **query-optimisation-and-graceful-restart-186.AC1.1:** `list_document_headers()` returns documents with all metadata columns populated (id, workspace_id, title, order_index, type, source_type, auto_number_paragraphs, created_at) — verify each field is accessible and has the expected value.

- **query-optimisation-and-graceful-restart-186.AC1.3:** Accessing `.content` on a headers-only object raises `DetachedInstanceError`. Use `pytest.raises(DetachedInstanceError)`.

- **query-optimisation-and-graceful-restart-186.AC1.4:** `list_documents()` still returns full content — verify `.content` is accessible and matches what was inserted.

Test setup: create a workspace with `create_workspace()`, add a document with known content via `add_document()`, then call both `list_document_headers()` and `list_documents()` to compare.

Follow the project's integration test patterns:
- Include `pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="...")` skip guard
- Class-based organisation (`class TestListDocumentHeaders`)
- `@pytest.mark.asyncio` on async test methods
- UUID-based isolation (each test creates its own workspace)
- Import DB functions inside test body

Reference files for patterns: `tests/integration/test_workspace_crud.py`, `tests/integration/test_document_crud.py`

**Verification:**
Run: `uv run grimoire test run tests/integration/test_document_headers.py`
Expected: All tests pass

**Commit:** `test: add integration tests for list_document_headers() (#186, #432)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## Complexipy Check

After completing this phase, run:
```bash
uv run complexipy src/promptgrimoire/db/workspace_documents.py src/promptgrimoire/pages/annotation/workspace.py src/promptgrimoire/pages/annotation/tab_bar.py src/promptgrimoire/pages/annotation/document_management.py --max-complexity-allowed 15
```

Flag any functions at complexity 10–15 as at-risk. File-level complexity >100 is a refactoring candidate.

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Navigate to an annotation workspace with 3+ documents
3. [ ] Verify: all document tabs render in the tab bar with correct titles
4. [ ] Verify: the first document's content is visible (HTML rendered with highlights)
5. [ ] Click "Manage Documents" — verify the dialog lists all documents with display names
6. [ ] Verify: paragraph numbering toggle in header works correctly

## Evidence Required
- [ ] `uv run grimoire test all` output showing green
- [ ] `uv run grimoire test run tests/integration/test_document_headers.py` output showing green
- [ ] Screenshot of annotation page with multi-doc tabs rendering correctly
