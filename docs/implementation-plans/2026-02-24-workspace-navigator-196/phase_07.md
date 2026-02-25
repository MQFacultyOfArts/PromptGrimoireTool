# Workspace Navigator Implementation Plan — Phase 7: Cursor Pagination UI

**Goal:** Add infinite scroll pagination so the navigator loads incrementally — initial 50 rows, then more as the user scrolls near the bottom.

**Architecture:** The navigator page wraps its content in a `ui.scroll_area` with an `on_scroll` callback. When `vertical_percentage` exceeds 0.9, the handler calls `load_navigator_page()` with the stored cursor to fetch the next batch, accumulates the new rows into the existing list, and calls `sections_refreshable.refresh()` to re-render all sections with the combined data. A loading guard prevents concurrent fetches. During an active search, infinite scroll is disabled (search operates on the full FTS result set, not paginated data).

**Tech Stack:** NiceGUI (`ui.scroll_area` with `on_scroll`), `@ui.refreshable`, existing `load_navigator_page()` with keyset cursor.

**Scope:** Phase 7 of 8

**Codebase verified:** 2026-02-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC5: Cursor pagination
- **workspace-navigator-196.AC5.1 Success:** Initial load shows first 50 rows across all sections
- **workspace-navigator-196.AC5.2 Success:** "Load more" fetches next 50 rows, appended into correct sections
  - *Deviation:* "Load more" is implemented as infinite scroll (automatic trigger at 90% scroll), not a button. The behaviour is the same — next batch is fetched and appended into correct sections.
- **workspace-navigator-196.AC5.3 Success:** Students with no workspaces (instructor view) appear at end of their unit section
- **workspace-navigator-196.AC5.4 Edge:** Total rows fewer than 50 — loads all in one page, no "Load more"
- **workspace-navigator-196.AC5.5 Edge:** Works correctly with 1100+ students in a single unit

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/pages/navigator.py` — Navigator page from Phase 4. Contains `@ui.refreshable` sections rendering, pagination state (`rows`, `next_cursor`, `user_id`, `is_privileged`, `enrolled_course_ids`). Phase 5 added search with debounce.
- `src/promptgrimoire/db/navigator.py:52-57` — `NavigatorCursor(section_priority, sort_key, row_id)` NamedTuple for keyset pagination.
- `src/promptgrimoire/db/navigator.py:263-349` — `load_navigator_page(user_id, is_privileged, enrolled_course_ids, cursor, limit)` returns `(list[NavigatorRow], NavigatorCursor | None)`. When `cursor` is `None`, loads first page. Returns `None` cursor when no more pages.
- `docs/nicegui/ui-patterns.md` — `@ui.refreshable` patterns, `ui.timer` patterns.

**`ui.scroll_area` pattern:**
```python
with ui.scroll_area(on_scroll=handle_scroll) as scroll:
    # content here
```
The `on_scroll` callback receives an event with properties including `vertical_percentage` (0.0 to 1.0), `vertical_size` (total scrollable height), and `vertical_position` (current scroll offset). Trigger loading at `vertical_percentage > 0.9`.

**Pagination state from Phase 4:**
Phase 4 Task 2 stores `rows`, `next_cursor`, and page-level context (user_id, is_privileged, enrolled_course_ids) in page-level state. Phase 7 uses these to load subsequent pages.

**Search interaction:**
When search is active (Phase 5), the navigator shows filtered results from FTS — not paginated data. Infinite scroll should be disabled during an active search. When search is cleared, the full paginated view resumes from wherever the user had scrolled to.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Wrap navigator content in scroll area with infinite scroll handler

**Verifies:** workspace-navigator-196.AC5.1, workspace-navigator-196.AC5.2, workspace-navigator-196.AC5.4, workspace-navigator-196.AC5.5

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

1. **Scroll area wrapper:** Wrap the main content area (search input + sections) in `ui.scroll_area(on_scroll=handle_scroll).classes('w-full')`. The scroll area needs a bounded viewport height so `on_scroll` fires. Prefer using CSS flexbox (`flex: 1; overflow: hidden` on the parent, `height: 100%` on the scroll area) so it fills the remaining viewport below the `page_layout` header naturally. If flexbox isn't feasible, use `style='height: calc(100vh - Npx)'` where N is the actual `page_layout` header height — verify this during implementation by inspecting the rendered header (Quasar default is ~64px but may vary). Without a bounded height, `on_scroll` will not fire because the area won't be independently scrollable.

2. **Infinite scroll handler:**
   ```python
   loading = False

   async def handle_scroll(e) -> None:
       nonlocal loading
       if loading:
           return
       if e.vertical_percentage < 0.9:
           return
       if next_cursor is None:
           return  # No more pages (AC5.4)
       if search_active:
           return  # Don't paginate during search

       loading = True
       try:
           new_rows, new_cursor = await load_navigator_page(
               user_id, is_privileged, enrolled_course_ids,
               cursor=next_cursor, limit=50,
           )
           rows.extend(new_rows)
           next_cursor = new_cursor
           sections_refreshable.refresh(rows, snippets={})
       finally:
           loading = False
   ```

3. **Loading guard:** The `loading` boolean prevents concurrent fetches when the user scrolls rapidly. Reset in `finally` to ensure recovery from errors.

4. **Search interaction:** Add a `search_active` flag (set `True` when search has filtered results, `False` when cleared). When `search_active is True`, the scroll handler returns early — search results are not paginated.

5. **No-more-pages state:** When `next_cursor is None` (returned by `load_navigator_page` when all rows are loaded), the scroll handler does nothing. No UI indicator needed — the user simply reaches the end of the list (AC5.4).

6. **Update `next_cursor` reference:** Ensure the scroll handler's closure captures the mutable `next_cursor` variable correctly. Use a mutable container (e.g., a list or dataclass) if Python scoping requires it, or use `nonlocal` if the handler is defined within the page function scope.

**Verification:**
Manual: Load navigator with seed data. Scroll to bottom — more rows load automatically. With fewer than 50 total rows, no additional loading occurs.
Run: `uv run test-changed`

**Commit:** `feat: add infinite scroll pagination to navigator`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Ensure new rows render into correct sections after load

**Verifies:** workspace-navigator-196.AC5.2, workspace-navigator-196.AC5.3

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

The `@ui.refreshable` sections renderer from Phase 4 already groups rows by section using a dict-based accumulator (NOT `itertools.groupby` — see Phase 4 Task 2). When `sections_refreshable.refresh(rows, snippets)` is called with the accumulated rows list, it re-renders all sections from scratch with the full dataset. This means:

1. **Correct section placement:** New rows from page 2+ are automatically grouped into their correct sections because the refreshable function re-renders the entire section list from the accumulated `rows`. No manual DOM insertion needed.

2. **Students with no workspaces (AC5.3):** The `load_navigator_page` query returns rows for students with no workspaces at the end of the `shared_in_unit` section (they have the lowest `sort_key` priority). As more pages load and these rows arrive, they appear at the end of their unit section after workspace-bearing students. No special handling needed — the data loader's sort order handles this.

3. **Scroll position preservation:** After `sections_refreshable.refresh()`, NiceGUI re-renders the content inside the scroll area. The `ui.scroll_area` should preserve its scroll position since only the inner content changes. If scroll position jumps to top after refresh, use `scroll_area.scroll_to(percent=previous_percent)` after refresh to restore position. Test this manually.

4. **Verify with large datasets:** Use the load-test seed data (1100+ students per unit from Phase 2) to verify pagination works correctly at scale (AC5.5).

**Verification:**
Manual: With load-test data, scroll through multiple pages. Verify rows appear in correct sections. Verify students with no workspaces appear at end of their unit section.
Run: `uv run test-changed`

**Commit:** `feat: verify section grouping with paginated data loading`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: E2E test — infinite scroll loads more rows

**Verifies:** workspace-navigator-196.AC5.1, workspace-navigator-196.AC5.2, workspace-navigator-196.AC5.4, workspace-navigator-196.AC5.5

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E tests for infinite scroll pagination using Playwright:

- AC5.1 + AC5.2: Set up test data with more than 50 workspace rows (e.g., 60 workspaces across sections). Navigate to `/`. Verify initial load shows approximately 50 rows. Scroll to the bottom of the scroll area. Wait for new content to appear. Verify total visible rows increased (more rows loaded).

- AC5.4: Set up test data with fewer than 50 total rows (e.g., 10 workspaces). Navigate to `/`. Verify all rows visible. Scroll to bottom. Verify no additional loading occurs (no spinner, no network activity, row count unchanged).

- AC5.5: Use load-test seed data or create 60+ rows via DB operations. Verify infinite scroll works through multiple page loads without errors or duplicate rows.

**Scroll simulation in Playwright:**
```python
# Scroll the NiceGUI scroll area to trigger on_scroll
await page.locator('.q-scrollarea').evaluate(
    'el => el.querySelector(".q-scrollarea__container").scrollTop = el.querySelector(".q-scrollarea__container").scrollHeight'
)
```
Or use `page.mouse.wheel(0, 10000)` within the scroll area bounds.

**Verification:**
Run: `uv run test-e2e -k test_navigator`

**Commit:** `test: add E2E tests for infinite scroll pagination`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E test — pagination disabled during search

**Verifies:** workspace-navigator-196.AC5.2 (interaction with search)

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E test verifying that infinite scroll is disabled during an active search:

- Set up test data with more than 50 rows.
- Navigate to `/`.
- Type a search query (3+ characters) that returns a subset of results.
- Wait for search results to render.
- Scroll to the bottom of the results.
- Verify no additional rows are loaded (the search result set is complete, not paginated).
- Clear search. Verify full paginated view restores. Scroll to bottom — verify pagination resumes.

**Verification:**
Run: `uv run test-e2e -k test_navigator`

**Commit:** `test: add E2E test for pagination disabled during search`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

---

## Next Phase

Phase 8 adds navigation chrome (home icon on annotation, roleplay, and courses pages) and i18n terminology ("Unit" not "Course" throughout the application).
