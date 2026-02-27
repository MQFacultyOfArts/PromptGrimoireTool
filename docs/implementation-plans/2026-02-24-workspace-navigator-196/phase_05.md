# Workspace Navigator Implementation Plan — Phase 5: Search

**Goal:** Add server-side search to the navigator. At 3+ characters with 500ms debounce, FTS fires and the navigator re-renders with only matching rows, each showing a `ts_headline` snippet.

**Architecture:** Purely server-side. The search input fires a debounced Python handler that calls `search_workspace_content()` to get matching workspace IDs + snippets, then re-queries `load_navigator_page()` filtered to those IDs (or re-renders with the intersection). The `@ui.refreshable` sections from Phase 4 re-render with the filtered data. Clearing search restores the full unfiltered view. No client-side JavaScript filtering.

**Tech Stack:** NiceGUI (`ui.input` with debounced event, `@ui.refreshable`), PostgreSQL FTS via `db/search.py`.

**Scope:** Phase 5 of 8

**Codebase verified:** 2026-02-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC3: Search
- **workspace-navigator-196.AC3.1 Deviation:** Typing filters visible workspaces by title, unit code, and activity name instantly (client-side)
  - *Deviation:* Filtering is server-side, not client-side. Triggers at 3+ chars with debounce, not on every keystroke. This is a design plan simplification — the tradeoff is a brief delay before results appear vs the complexity of a client-side JS layer.
- **workspace-navigator-196.AC3.2 Success:** At >=3 characters, FTS fires (with debounce) and surfaces content matches with `ts_headline` snippet
- **workspace-navigator-196.AC3.4 Success:** FTS results that weren't visible from title match show a content snippet explaining the match
- **workspace-navigator-196.AC3.5 Edge:** Clearing search restores full unfiltered list
- **workspace-navigator-196.AC3.6 Edge:** Search with no results shows "No workspaces match" with clear option

### workspace-navigator-196.AC8: FTS infrastructure (short query edge)
- **workspace-navigator-196.AC8.4 Edge:** Short queries (<3 chars) do not trigger FTS

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/pages/navigator.py` — Navigator page from Phase 4. Sections rendered via `@ui.refreshable` function that accepts rows and optional snippets dict.
- `src/promptgrimoire/db/search.py:30-44` — `FTSResult` dataclass: `workspace_id: UUID`, `snippet: str` (HTML with `<mark>` tags), `rank: float`, `source: str`.
- `src/promptgrimoire/db/search.py:47-162` — `search_workspace_content(query: str, workspace_ids: Sequence[UUID] | None = None, limit: int = 50) -> list[FTSResult]`. Requires query of at least 3 chars.
- `src/promptgrimoire/db/navigator.py:263-349` — `load_navigator_page()` returns `(list[NavigatorRow], NavigatorCursor | None)`.
- `docs/nicegui/ui-patterns.md` — `@ui.refreshable` patterns, `ui.timer` for debounce.

**Search flow:**
1. User types in search input.
2. On each change, if `len(query) >= 3`, start a 500ms debounce timer (cancel previous).
3. When debounce fires, call `search_workspace_content(query)` → get `list[FTSResult]`.
4. Build `snippets: dict[UUID, str]` mapping workspace IDs to snippets.
5. Filter the current `rows` to only those whose `workspace_id` is in the FTS results.
6. Call `sections_refreshable.refresh(filtered_rows, snippets)` to re-render.
7. If no results, show "No workspaces match" with a clear option.
8. On clear (or query < 3 chars), call `sections_refreshable.refresh(all_rows, {})` to restore full view.

**Debounce pattern:** Use `ui.timer(0.5, callback, once=True)`. Cancel previous timer on each keystroke. This avoids any client-side JS.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add search input with debounced FTS handler

**Verifies:** workspace-navigator-196.AC3.2, workspace-navigator-196.AC3.5, workspace-navigator-196.AC3.6, workspace-navigator-196.AC8.4

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

1. **Search input:** Add `ui.input(placeholder="Search titles and content...")` at the top of the main content area (below page_layout header, above sections). Full width, prominent styling.

2. **Debounce timer:** Maintain a reference to a `ui.timer` instance. On each input change:
   - If previous timer exists, deactivate it.
   - If `len(query.strip()) < 3`: restore full unfiltered view by calling `sections_refreshable.refresh(all_rows, {})`. Clear any "no results" state. Do NOT trigger FTS (AC8.4).
   - If `len(query.strip()) >= 3`: create `ui.timer(0.5, lambda: asyncio.ensure_future(do_search(query)), once=True)`.

3. **Search handler (`do_search`):**
   ```python
   async def do_search(query: str) -> None:
       results = await search_workspace_content(query, limit=50)
       matched_ids = {r.workspace_id for r in results}
       snippets = {r.workspace_id: r.snippet for r in results}
       filtered = [r for r in all_rows if r.workspace_id in matched_ids]
       sections_refreshable.refresh(filtered, snippets)
   ```

4. **No results state:** If `filtered` is empty after FTS, render "No workspaces match your search" with a "Clear" button that resets the search input and calls `sections_refreshable.refresh(all_rows, {})`.

5. **Clear on empty:** When query becomes empty or < 3 chars, restore full view (AC3.5).

**Verification:**
Manual: Type 3+ characters. After ~500ms, sections re-render with filtered results. Clear search — full view returns.
Run: `uv run test-changed`

**Commit:** `feat: add server-side search with debounce to navigator`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Render FTS snippets on matching workspace cards

**Verifies:** workspace-navigator-196.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

Update the `@ui.refreshable` sections rendering function to display snippets:

1. The function already accepts `snippets: dict[UUID, str]` (set up in Phase 4).
2. When rendering a workspace entry, check if `row.workspace_id in snippets`.
3. If present, render the snippet below the title using `ui.html(snippets[row.workspace_id])` — the snippet contains `<mark>` tags from `ts_headline`.
4. Add subtle CSS styling for the snippet area (smaller text, light background).

**Verification:**
Manual: Search for a word in document content. Matching cards show highlighted snippet text below the title.
Run: `uv run test-changed`

**Commit:** `feat: render FTS snippets on matching navigator cards`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add CSS for search snippets

**Verifies:** workspace-navigator-196.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

Add CSS via `ui.add_css()` in the navigator page for snippet rendering:
- Snippet container: smaller text, subtle background, rounded corners, below title.
- `mark` elements within snippets: visible highlight colour for matched terms.

**Verification:**
Visual: Snippets render cleanly with highlighted terms.

**Commit:** `feat: add CSS for navigator search snippets`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: E2E test — search filters and restores

**Verifies:** workspace-navigator-196.AC3.2, workspace-navigator-196.AC3.5, workspace-navigator-196.AC3.6, workspace-navigator-196.AC8.4

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E tests for search using Playwright:

- AC3.2: Type 3+ characters matching document content (not title). Wait for debounce. Verify filtered results appear with snippet.
- AC3.5: Type a search query, then clear the input. Verify full unfiltered view returns.
- AC3.6: Type a query matching nothing. Verify "No workspaces match" message. Click "Clear" — verify full view returns.
- AC8.4: Type only 2 characters. Wait 1 second. Verify no filtering occurs (all rows still visible).

**Verification:**
Run: `uv run test-e2e -k test_navigator`

**Commit:** `test: add E2E tests for navigator search`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

---

## Next Phase

Phase 6 adds inline workspace title rename (pencil icon, readonly toggle, blur/Enter saves, Escape cancels).
