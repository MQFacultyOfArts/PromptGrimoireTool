# Paragraph Numbering Implementation Plan — Phase 3: Document Save Integration

**Goal:** Build and store the paragraph map when documents are created or cloned.

**Architecture:** After `process_input()` returns clean HTML, the paste-in and file upload handlers call `detect_source_numbering()` + `build_paragraph_map()`, then pass results to `add_document()`. Cloning copies both fields verbatim.

**Tech Stack:** NiceGUI async handlers, SQLModel

**Scope:** Phase 3 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### paragraph-numbering-191.AC3: Auto-detection on paste-in
- **paragraph-numbering-191.AC3.1 Success:** Pasting HTML with 2+ `<li value>` elements sets `auto_number_paragraphs = False`
- **paragraph-numbering-191.AC3.2 Success:** Pasting HTML with 0-1 `<li value>` elements sets `auto_number_paragraphs = True`

(AC3.3 — upload dialog with override checkbox — is deferred to Phase 7: Toggle UI)

---

## Reference Files

The executor MUST read these before implementing:
- `src/promptgrimoire/pages/annotation/content_form.py` — paste-in handler (~line 554), file upload handler (~line 605)
- `src/promptgrimoire/db/workspace_documents.py` — `add_document()` (~line 20)
- `src/promptgrimoire/db/workspaces.py` — workspace cloning, document cloning (~line 649)
- `CLAUDE.md` — testing conventions

---

<!-- START_TASK_1 -->
### Task 1: Extend `add_document()` to accept paragraph fields

**Files:**
- Modify: `src/promptgrimoire/db/workspace_documents.py:20-62`

**Implementation:**

Add two optional parameters to `add_document()`:

```python
async def add_document(
    workspace_id: UUID,
    type: str,
    content: str,
    source_type: str,
    title: str | None = None,
    auto_number_paragraphs: bool = True,
    paragraph_map: dict[str, int] | None = None,
) -> WorkspaceDocument:
```

In the `WorkspaceDocument(...)` constructor call, add:
```python
auto_number_paragraphs=auto_number_paragraphs,
paragraph_map=paragraph_map if paragraph_map is not None else {},
```

Default `paragraph_map` to `{}` if not provided, matching the model default. Existing callers pass no paragraph args and get defaults.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: extend add_document() to accept paragraph numbering fields`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire detection + mapping into paste-in handler

**Verifies:** paragraph-numbering-191.AC3.1, AC3.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/content_form.py` (~lines 580-591)

**Implementation:**

After `process_input()` returns `processed_html` (around line 584), add:

```python
from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map,
    detect_source_numbering,
)

auto_number = not detect_source_numbering(processed_html)
para_map = build_paragraph_map(processed_html, auto_number=auto_number)
```

Then pass to `add_document()`:
```python
await add_document(
    workspace_id=workspace_id,
    type="source",
    content=processed_html,
    source_type=confirmed_type,
    title=None,
    auto_number_paragraphs=auto_number,
    paragraph_map=para_map,
)
```

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: auto-detect paragraph numbering on paste-in`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Wire detection + mapping into file upload handler

**Verifies:** paragraph-numbering-191.AC3.1, AC3.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/content_form.py` (~lines 628-639)

**Implementation:**

Same pattern as paste-in handler. After `process_input()` returns `processed_html`:

```python
auto_number = not detect_source_numbering(processed_html)
para_map = build_paragraph_map(processed_html, auto_number=auto_number)
```

Pass both to `add_document()` alongside the existing `title=filename`.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: auto-detect paragraph numbering on file upload`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Copy paragraph fields in workspace cloning

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (~lines 649-670, document cloning loop)

**Implementation:**

In the `WorkspaceDocument(...)` constructor inside the clone loop, add:

```python
cloned_doc = WorkspaceDocument(
    workspace_id=clone.id,
    type=tmpl_doc.type,
    content=tmpl_doc.content,
    source_type=tmpl_doc.source_type,
    title=tmpl_doc.title,
    order_index=tmpl_doc.order_index,
    auto_number_paragraphs=tmpl_doc.auto_number_paragraphs,
    paragraph_map=tmpl_doc.paragraph_map,
)
```

**Verification:**
```bash
uvx ty check
```

**Verification:**
```bash
uvx ty check
uv run pytest tests/integration/ -v -k "clone" --no-header
```
Expected: Type check clean and existing clone integration tests still pass.

**Commit:** `feat: preserve paragraph numbering fields during workspace cloning`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Integration tests for document save with paragraph fields

**Verifies:** paragraph-numbering-191.AC3.1, AC3.2

**Files:**
- Modify: `tests/integration/test_paragraph_numbering.py` (add to existing file from Phase 1)

**Testing:**

Add to the existing test file:

**`TestAddDocumentWithParagraphFields`:**
- Test that `add_document()` with explicit `auto_number_paragraphs=False` and a populated `paragraph_map` persists correctly and round-trips
- Test that `add_document()` with no paragraph args uses defaults (`True`, `{}`)

**`TestClonePreservesParagraphFields`:**
- Test that cloning a workspace with a document that has `auto_number_paragraphs=False` and a populated `paragraph_map` produces a clone with identical values
- Requires creating a workspace, adding a document with paragraph fields, cloning, then verifying the clone's document

Follow the existing integration test patterns in `tests/integration/test_workspace_crud.py` — class-based, `db_session` fixture, skip guard.

**Verification:**
```bash
uv run pytest tests/integration/test_paragraph_numbering.py -v
```
Expected: All tests pass (Phase 1 + Phase 3 tests).

**Commit:** `test: add integration tests for paragraph fields in save and clone paths`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Backfill script for existing documents

**Files:**
- Create: `scripts/backfill_paragraph_maps.py`

**Implementation:**

Create a one-time backfill script that:
1. Connects to the database using the application's settings
2. Queries all `WorkspaceDocument` rows where `paragraph_map` is empty (`{}`)
3. For each document, calls `detect_source_numbering(doc.content)` to determine mode
4. Calls `build_paragraph_map(doc.content, auto_number=auto_number)` to build the map
5. Updates the document's `auto_number_paragraphs` and `paragraph_map` fields
6. Commits in batches (e.g., 50 documents per commit) to avoid long transactions
7. Reports progress: number of documents processed, any errors

The script should be idempotent — running it twice should be safe (skip documents that already have a non-empty map, or rebuild all).

Add a `pyproject.toml` script entry:
```toml
backfill-paragraph-maps = "scripts.backfill_paragraph_maps:main"
```

**Verification:**
```bash
uv run backfill-paragraph-maps --dry-run
```
Expected: Reports how many documents would be updated without modifying data.

```bash
uv run backfill-paragraph-maps
```
Expected: Updates all existing documents with computed paragraph maps.

**Commit:** `feat: add backfill script for existing document paragraph maps`
<!-- END_TASK_6 -->

---

## UAT Steps

1. [ ] Run all integration tests: `uv run pytest tests/integration/test_paragraph_numbering.py -v` — all pass
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Paste an AustLII document (with `<li value>` attributes) — check DB: `auto_number_paragraphs` should be `False`
4. [ ] Paste a plain HTML document — check DB: `auto_number_paragraphs` should be `True`
5. [ ] Run backfill (dry-run): `uv run backfill-paragraph-maps --dry-run` — reports existing document count
6. [ ] Run backfill: `uv run backfill-paragraph-maps` — updates existing documents

## Evidence Required
- [ ] Integration test output all green
- [ ] Backfill script output showing documents processed
