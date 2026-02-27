# Workspace Navigator Implementation Plan — Phase 1: FTS Infrastructure

**Goal:** Full-text search across all workspace text: source documents, annotation comments, tag names, and response drafts.

**Architecture:** Two GIN expression indexes — one on `workspace_document.content` (HTML-stripped source text) and one on `workspace.search_text` (materialised CRDT content). A pure extraction function deserialises CRDT state and concatenates comment text, tag names, and response draft markdown. The CRDT persistence pipeline sets `search_dirty=True` on save; an async worker polls for dirty workspaces, runs extraction, and writes to `search_text`. A single `db/search.py` module queries both indexes via `websearch_to_tsquery` with `ts_headline` snippets.

**Tech Stack:** PostgreSQL FTS (tsvector, GIN expression indexes, websearch_to_tsquery, ts_headline), pycrdt deserialization, SQLAlchemy `text()` queries, Alembic manual migration.

**Scope:** Phase 1 of revised plan (phases 1-3 cover FTS, load-test data, SQL query)

**Codebase verified:** 2026-02-25

**Design deviations:**
- Design plan specifies a "generated `tsvector` column." PostgreSQL's `to_tsvector()` is not immutable, so it cannot be used in `GENERATED ALWAYS AS STORED` columns. GIN expression indexes achieve the same query performance.
- Design plan scopes FTS to `workspace_document.content` only. Expanded to include CRDT-sourced text (annotation comments, tag names, response draft) via `workspace.search_text` column and lazy extraction worker.
- Design plan specifies `to_tsquery`. Plan uses `websearch_to_tsquery` instead — safe for arbitrary user input (handles natural language queries, quoted phrases), superset behaviour.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC8: FTS infrastructure
- **workspace-navigator-196.AC8.1 Success:** `workspace_document` table has generated `tsvector` column with GIN index
  - *Adapted:* GIN expression index on `to_tsvector('english', regexp_replace(content, '<[^>]+>', ' ', 'g'))` — equivalent query performance, no stored column.
- **workspace-navigator-196.AC8.2 Success:** HTML tags stripped from indexed content (not indexed as words)
- **workspace-navigator-196.AC8.3 Success:** `ts_headline` returns snippet with matched terms highlighted
- **workspace-navigator-196.AC8.4 Edge:** Short queries (<3 chars) do not trigger FTS
- **workspace-navigator-196.AC8.5 Edge:** Empty document content produces valid (empty) tsvector, no errors

### workspace-navigator-196.AC3: Search (partial — FTS query layer only)
- **workspace-navigator-196.AC3.2 Success:** At >=3 characters, FTS fires (with debounce) and surfaces content matches with `ts_headline` snippet
  - *This phase:* query helper returns matches with snippets. Debounce and UI wiring are Phase 4 (Search).
- **workspace-navigator-196.AC3.4 Success:** FTS results that weren't visible from title match show a content snippet explaining the match
  - *This phase:* snippet generation via `ts_headline`. Display logic is Phase 4.

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/db/models.py` — Workspace (line 312), WorkspaceDocument (line 362), Tag (line 423). Workspace has no search columns yet.
- `src/promptgrimoire/crdt/annotation_doc.py` — AnnotationDocument class (line 40). Read-only accessors: `get_all_highlights()` (line 322), `get_response_draft_markdown()` (line 118), `get_general_notes()` (line 110). Highlight dicts have `"tag"` (str, may be UUID or legacy name), `"text"` (highlighted text), `"comments"` (list of `{"text": str, ...}`).
- `src/promptgrimoire/crdt/persistence.py` — PersistenceManager (line 21). `_persist_workspace()` (line 106) is the save hook point. Debounce at 5 seconds (line 30).
- `src/promptgrimoire/db/workspaces.py` — `save_workspace_crdt_state()` (line 312).
- `src/promptgrimoire/db/tags.py` — Tag CRUD functions. Will need a bulk lookup: tag UUIDs → tag names for a workspace.
- `alembic/versions/` — Current head: `1184bd94f104_add_sharing_columns`. Use `op.execute()` for expression indexes.
- `docs/testing.md` — Integration test patterns: skip guard, class-based grouping, `@pytest.mark.asyncio`, `db_session` fixture.

**Critical patterns:**
- `session.execute(text(...), params)` for raw SQL — used in `tags.py:72-76`
- `get_session()` context manager from `db/engine.py` for async DB access
- CRDT deserialization: `doc = AnnotationDocument(); doc.apply_update(crdt_state_bytes)`
- Tag field in highlights is a string — may be a UUID (DB-backed tag) or legacy BriefTag string. Resolve UUID strings to Tag.name via DB lookup; pass non-UUID strings through as-is.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Alembic migration — FTS columns and indexes

**Verifies:** workspace-navigator-196.AC8.1, workspace-navigator-196.AC8.2

**Files:**
- Create: `alembic/versions/<generated>_add_fts_infrastructure.py`

**Implementation:**

Create migration manually (Alembic autogenerate cannot detect expression indexes):

```bash
uv run alembic revision -m "add FTS infrastructure"
```

The migration adds:
1. `search_text` column (nullable Text) on `workspace` — stores materialised CRDT text
2. `search_dirty` column (Boolean, server_default='true') on `workspace` — worker queue flag
3. GIN expression index `idx_workspace_document_fts` on `workspace_document` using `to_tsvector('english', regexp_replace(content, '<[^>]+>', ' ', 'g'))`
4. GIN expression index `idx_workspace_search_text_fts` on `workspace` using `to_tsvector('english', COALESCE(search_text, ''))`

Use `op.add_column()` for columns, `op.execute()` for GIN indexes. Downgrade drops indexes then columns.

**Verification:**
Run: `uv run alembic upgrade head`
Expected: Migration applies without errors.

Verify indexes exist:
```sql
SELECT indexname FROM pg_indexes
WHERE tablename IN ('workspace_document', 'workspace')
AND indexname LIKE 'idx_%_fts%';
```
Expected: Two rows (`idx_workspace_document_fts`, `idx_workspace_search_text_fts`).

**Commit:** `feat: add FTS columns and GIN expression indexes`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Workspace model update — search_text and search_dirty fields

**Verifies:** None (infrastructure — type checker verifies)

**Files:**
- Modify: `src/promptgrimoire/db/models.py` (Workspace class, line 312)

**Implementation:**

Add two fields to the Workspace class:

```python
search_text: str | None = Field(
    default=None, sa_column=Column(sa.Text(), nullable=True)
)
search_dirty: bool = Field(
    default=True,
    sa_column=Column(sa.Boolean(), nullable=False, server_default="true"),
)
```

Place after `shared_with_class` (line 345) and before `created_at` (line 346).

**Verification:**
Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add search_text and search_dirty fields to Workspace model`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: CRDT text extraction function

**Verifies:** workspace-navigator-196.AC8.5 (empty content handling)

**Files:**
- Create: `src/promptgrimoire/db/search.py`
- Test: `tests/unit/test_search_extraction.py` (unit — no database)

**Implementation:**

Create `src/promptgrimoire/db/search.py` with a pure function:

```python
def extract_searchable_text(
    crdt_state: bytes | None,
    tag_names: dict[str, str],
) -> str:
```

This function:
1. Returns empty string if `crdt_state` is None.
2. Deserialises CRDT state via `AnnotationDocument.apply_update(crdt_state)`.
3. Iterates `doc.get_all_highlights()`. For each highlight:
   - Collects `highlight["text"]` (the highlighted source text).
   - Resolves `highlight["tag"]` via `tag_names` dict (UUID string → tag name). If tag string is not in `tag_names`, includes it as-is (legacy BriefTag string).
   - Collects `comment["text"]` from each comment in `highlight.get("comments", [])`.
4. Reads `doc.get_response_draft_markdown()` — the Tab 3 response draft.
5. Reads `doc.get_general_notes()` — general workspace notes.
6. Concatenates all text with newline separators and returns.

The `tag_names` dict is pre-built by the caller (worker) via a single DB query. This keeps the extraction function pure and unit-testable.

**Testing:**

Unit tests (no database):
- Create an AnnotationDocument programmatically, add highlights with comments and tags, serialise to bytes. Pass to `extract_searchable_text()`. Verify output contains comment text, tag names, response draft, and general notes.
- Pass `crdt_state=None` — returns empty string (AC8.5 edge case).
- Highlight with tag UUID present in `tag_names` → resolved name appears in output.
- Highlight with tag UUID NOT in `tag_names` → raw string appears in output (graceful fallback).
- Response draft markdown included in output.
- General notes included in output.

**Verification:**
Run: `uv run test-changed`
Expected: All new unit tests pass.

**Commit:** `feat: add CRDT text extraction for FTS indexing`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Persistence hook — set search_dirty on CRDT save

**Verifies:** None (infrastructure wiring — integration tested in Task 6)

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` — `save_workspace_crdt_state()` (line 312)

**Implementation:**

In `save_workspace_crdt_state()`, after setting `workspace.crdt_state = crdt_state` and `workspace.updated_at`, also set:

```python
workspace.search_dirty = True
```

This ensures every CRDT save marks the workspace for re-extraction by the worker. The flag is set alongside the blob write in the same transaction — no additional query.

**Verification:**
Run: `uvx ty check`
Expected: No type errors.

Additionally, add one integration test case to `tests/integration/test_fts_search.py` (or a dedicated class in that file) that calls `save_workspace_crdt_state()` with test CRDT bytes and verifies `workspace.search_dirty` is `True` in the database after the call.

**Commit:** `feat: mark workspace search_dirty on CRDT save`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-7) -->
<!-- START_TASK_5 -->
### Task 5: Search extraction worker

**Verifies:** None directly (worker is infrastructure — tested via integration test in Task 6)

**Files:**
- Create: `src/promptgrimoire/search_worker.py`

**Implementation:**

An async worker that polls for dirty workspaces and runs text extraction:

```python
async def process_dirty_workspaces(batch_size: int = 50) -> int:
```

This function:
1. Queries workspaces where `search_dirty = True`, limited to `batch_size`.
2. For each workspace:
   a. Loads tags for the workspace (bulk query: `SELECT id, name FROM tag WHERE workspace_id = :ws_id`) to build `tag_names: dict[str, str]` mapping `str(tag.id)` → `tag.name`.
   b. Calls `extract_searchable_text(workspace.crdt_state, tag_names)`.
   c. Updates `workspace.search_text = extracted_text` and `workspace.search_dirty = False`.
3. Returns count of processed workspaces.

A second function starts the polling loop:

```python
async def start_search_worker(interval_seconds: float = 30.0) -> None:
```

This runs `process_dirty_workspaces()` in a loop with `asyncio.sleep(interval_seconds)` between iterations. Catches and logs exceptions per iteration (never crashes the loop).

The worker is started from the app's startup hook (existing NiceGUI `app.on_startup` pattern). It runs as a background asyncio task.

**Backlog note:** At batch_size=50 and 30s interval, the worker processes ~100 workspaces/minute. After running the Phase 2 load-test fixture (~2500+ dirty workspaces), initial catchup takes ~25 minutes. FTS queries against `workspace.search_text` will return incomplete results until the worker finishes processing the backlog. This is expected behaviour for a background job.

**Verification:**
Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add search extraction worker for dirty workspaces`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: FTS query helper — search_workspace_content()

**Verifies:** workspace-navigator-196.AC8.2, workspace-navigator-196.AC8.3, workspace-navigator-196.AC8.4, workspace-navigator-196.AC8.5, workspace-navigator-196.AC3.2 (partial), workspace-navigator-196.AC3.4 (partial)

**Files:**
- Modify: `src/promptgrimoire/db/search.py` (add to file created in Task 3)
- Test: `tests/integration/test_fts_search.py` (integration — requires PostgreSQL)

**Implementation:**

Add to `src/promptgrimoire/db/search.py`:

```python
@dataclasses.dataclass(frozen=True, slots=True)
class FTSResult:
    workspace_id: UUID
    snippet: str
    rank: float
    source: str  # "document" or "workspace"

async def search_workspace_content(
    query: str,
    workspace_ids: Sequence[UUID] | None = None,
    limit: int = 50,
) -> list[FTSResult]:
```

Key behaviours:
- Returns early (empty list) if `query.strip()` has fewer than 3 characters (AC8.4).
- Uses `websearch_to_tsquery('english', :query)` — safe for any user input.
- Queries **both** indexes:
  - `workspace_document.content`: WHERE expression matches GIN index exactly: `to_tsvector('english', regexp_replace(content, '<[^>]+>', ' ', 'g')) @@ websearch_to_tsquery('english', :query)`. Source: `"document"`.
  - `workspace.search_text`: WHERE `to_tsvector('english', COALESCE(search_text, '')) @@ websearch_to_tsquery('english', :query)`. Source: `"workspace"`.
- UNION the two result sets (different tables, different snippet sources).
- `ts_headline` options: `MaxWords=35, MinWords=15, MaxFragments=3, StartSel=<mark>, StopSel=</mark>`.
- Optionally filters by `workspace_ids` when provided (for scoping to accessible workspaces).
- Orders by `ts_rank` descending, limited to `limit` rows.
- Uses `get_session()` internally (no session parameter — follows project pattern for service-layer functions).

**Testing:**

Integration tests (require PostgreSQL with FTS indexes applied):

Module-level skip guard for `DEV__TEST_DATABASE_URL`. Class-based grouping. `@pytest.mark.asyncio` on all tests.

Tests must verify each AC listed above:
- workspace-navigator-196.AC8.2: Insert a workspace_document with `<p>The quick <b>brown</b> fox</p>`, search "brown fox" — should match (HTML stripped from index).
- workspace-navigator-196.AC8.3: Verify returned `snippet` field contains `<mark>` tags around matched terms.
- workspace-navigator-196.AC8.4: Search with query "ab" (2 chars) returns empty list without hitting the database.
- workspace-navigator-196.AC8.5: Insert document with empty content `""`, search any term — no error, document not in results.
- workspace-navigator-196.AC3.2 (partial): Search returns results with snippets for matching content.
- workspace-navigator-196.AC3.4 (partial): Search for text that appears in CRDT comment (set workspace.search_text directly) — returns result with snippet from search_text.

Additional test cases:
- Malformed query input (e.g., `"legal &"`) — returns results for "legal" without error.
- `workspace_ids` filter restricts results to specified workspaces only.
- Results ordered by relevance (document with more matches ranks higher).
- Workspace with `search_text = NULL` — no error, workspace not in results for that index.
- Search matches in both document content and workspace search_text — both results returned with correct `source` field.

**Verification:**
Run: `uv run test-changed`
Expected: All new tests pass.

**Commit:** `feat: add FTS query helper searching documents and CRDT content`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Wire search worker into app startup

**Verifies:** None (infrastructure wiring)

**Files:**
- Modify: `src/promptgrimoire/__main__.py` (or wherever `app.on_startup` hooks are registered)

**Implementation:**

Add the search worker to the NiceGUI app startup sequence. Find the existing `app.on_startup` pattern and add:

```python
from promptgrimoire.search_worker import start_search_worker

app.on_startup(start_search_worker)
```

The worker will start polling for dirty workspaces when the app boots. It runs as a background asyncio task and does not block the event loop.

If the app has no existing `on_startup` pattern, check how NiceGUI lifecycle hooks are used in the codebase (see `docs/nicegui/lifecycle.md`).

**Verification:**
Run: `uvx ty check`
Expected: No type errors.

Start the app (`uv run python -m promptgrimoire`), verify no errors in startup logs related to the search worker.

**Commit:** `feat: wire search worker into app startup`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->
