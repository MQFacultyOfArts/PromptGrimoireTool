# Workspace Navigator -- Test Requirements

## Scope

This document maps every acceptance criterion from the [design plan](../../design-plans/2026-02-24-workspace-navigator-196.md) to either automated tests or human verification procedures.

**All 8 phases are covered.**

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | FTS infrastructure (indexes, extraction, query helper) | Implemented |
| Phase 2 | Load-test fixture (1100-student dataset) | Implemented |
| Phase 3 | Navigator SQL query (UNION ALL data loader, integration tests) | Implemented |
| Phase 4 | Navigator page (core rendering, navigation, clone) | Planned |
| Phase 5 | Search (server-side FTS with debounce) | Planned |
| Phase 6 | Inline title rename | Planned |
| Phase 7 | Cursor pagination UI (infinite scroll) | Planned |
| Phase 8 | Navigation chrome and i18n | Planned |

---

## Approved Deviations from Design Plan

| AC ID | Design Plan Says | Implementation Does | Rationale |
|-------|-----------------|---------------------|-----------|
| AC3.1 | Client-side title/metadata filter from keystroke 1 | Server-side filtering at 3+ chars with 500ms debounce | Simplifies architecture by removing client-side JS filter layer. Tradeoff: brief delay before results appear vs complexity of maintaining parallel client/server filter states. |
| AC5.2 | "Load more" button fetches next 50 rows | Infinite scroll (automatic trigger at 90% scroll position) | Same data-loading behaviour, more modern UX. Rows are still fetched in 50-row batches and appended into correct sections. |
| AC7.1 | All user-facing text displays "Unit" not "Course" | Already implemented in codebase -- no changes needed | A previous codebase-wide rename already replaced "Course" with "Unit" in all user-facing text. Phase 8 verifies this holds and adds the configurable setting (AC7.2). |

---

## Automated Test Matrix

### AC1: Navigator page renders all sections

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC1.1 | Student sees "My Work" with owned workspaces grouped by unit > week > activity | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.1 | (UI rendering) Sections render with correct grouping and headers | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 4 | Planned |
| AC1.2 | Student sees "Unstarted Work" with published activities not yet started | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.2 | (UI rendering) Unstarted Work section visible with activity entries | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 4 | Planned |
| AC1.3 | Student sees "Shared With Me" with editor/viewer ACL workspaces | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.4 | Student sees "Shared in [Unit]" with peer workspaces grouped by anonymised student | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Partial |
| AC1.5 | Instructor sees "Shared in [Unit]" with all student workspaces by real student name | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.6 | Loose workspaces (no activity) appear under "Unsorted" in student grouping | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.7 | Empty sections hidden (produce zero rows) | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.7 | (UI rendering) Empty sections not rendered in DOM | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 4 | Planned |
| AC1.8 | Multi-enrolled student sees separate "Shared in [Unit]" per unit | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |

**Notes on AC1.4 (Partial):** Phase 3 tests verify the raw query returns correct rows with `owner_display_name` for the peer section. Anonymisation is applied at the rendering layer (Python, not SQL), so the integration test verifies data correctness but not the anonymised display. Full verification requires E2E testing (Phase 4 Task 4) or human verification.

### AC2: Workspace navigation

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC2.1 | Title click navigates to `/annotation?workspace_id=<uuid>` | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 4 | Planned |
| AC2.2 | Action button (Resume/Open/View) navigates to workspace | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 4 | Planned |
| AC2.3 | [Start] on unstarted activity clones template and navigates | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 5 | Planned |
| AC2.4 | Each workspace entry shows `updated_at` | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Partial |
| AC2.5 | Unauthenticated user redirected to login | E2E | `tests/e2e/test_navigator.py` | Phase 4 / Task 4 | Planned |

**Notes on AC2.4 (Partial):** Phase 3 integration tests verify that `updated_at` is present in the query output. The visual rendering of the date (formatted display on each workspace entry) is verified via E2E or manual inspection in Phase 4.

### AC3: Search

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC3.1 | Server-side filter by title/unit/activity at 3+ chars with debounce (deviation) | E2E | `tests/e2e/test_navigator.py` | Phase 5 / Task 4 | Planned |
| AC3.2 | FTS fires at >=3 chars with debounce, surfaces content matches with snippet | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Partial |
| AC3.2 | (UI wiring) Debounced FTS fires from navigator search input, results rendered | E2E | `tests/e2e/test_navigator.py` | Phase 5 / Task 4 | Planned |
| AC3.4 | FTS results show content snippet explaining the match | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Partial |
| AC3.4 | (UI rendering) Snippet displayed below workspace title on matching cards | E2E | `tests/e2e/test_navigator.py` | Phase 5 / Task 4 | Planned |
| AC3.5 | Clearing search restores full unfiltered list | E2E | `tests/e2e/test_navigator.py` | Phase 5 / Task 4 | Planned |
| AC3.6 | No results shows "No workspaces match" with clear option | E2E | `tests/e2e/test_navigator.py` | Phase 5 / Task 4 | Planned |

**Notes on AC3.2 and AC3.4 (Partial):** Phase 1 / Task 6 tests verify the FTS query helper returns correct results with `ts_headline` snippets. The debounce trigger logic, UI wiring, and display of snippet beneath workspace cards are Phase 5 concerns verified via E2E.

### AC4: Inline title rename

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC4.1 | Pencil icon activates inline edit | E2E | `tests/e2e/test_navigator.py` | Phase 6 / Task 3 | Planned |
| AC4.2 | Enter or blur saves new title | E2E | `tests/e2e/test_navigator.py` | Phase 6 / Task 3 | Planned |
| AC4.3 | Escape cancels edit without saving | E2E | `tests/e2e/test_navigator.py` | Phase 6 / Task 3 | Planned |
| AC4.4 | New workspaces default title to activity name | Integration | `tests/integration/test_navigator_loader.py` or clone tests | Phase 6 / Task 1 | Planned |
| AC4.4 | (UI rendering) Cloned workspace shows activity name as title on navigator | E2E | `tests/e2e/test_navigator.py` | Phase 6 / Task 4 | Planned |
| AC4.5 | Pencil click does not navigate (only title click navigates) | E2E | `tests/e2e/test_navigator.py` | Phase 6 / Task 3 | Planned |

**Notes on AC4.4:** Phase 6 / Task 1 modifies `clone_workspace_from_activity()` to set `title=activity.title` on the cloned workspace. This is tested at the integration level (clone function returns workspace with correct title) and at E2E level (navigator shows the activity name as default title after clicking Start).

### AC5: Cursor pagination

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC5.1 | Initial load shows first 50 rows | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.1 | (UI rendering) Initial page renders up to 50 rows across sections | E2E | `tests/e2e/test_navigator.py` | Phase 7 / Task 3 | Planned |
| AC5.2 | Infinite scroll fetches next 50, appended into correct sections (deviation) | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Partial |
| AC5.2 | (UI behaviour) Scrolling near bottom triggers load, new rows appear in correct sections | E2E | `tests/e2e/test_navigator.py` | Phase 7 / Task 3 | Planned |
| AC5.2 | (Search interaction) Infinite scroll disabled during active search | E2E | `tests/e2e/test_navigator.py` | Phase 7 / Task 4 | Planned |
| AC5.3 | Students with no workspaces (instructor view) appear at end of unit section | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.3 | (UI rendering) No-workspace students render at end of unit section | E2E | `tests/e2e/test_navigator.py` | Phase 7 / Task 3 | Planned |
| AC5.4 | Fewer than 50 rows -- all returned, no infinite scroll trigger | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.4 | (UI behaviour) No loading indicator when all data already present | E2E | `tests/e2e/test_navigator.py` | Phase 7 / Task 3 | Planned |
| AC5.5 | Works correctly with 1100+ students | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.5 | (UI behaviour) Infinite scroll handles 1100+ students without degradation | E2E | `tests/e2e/test_navigator.py` | Phase 7 / Task 3 | Planned |

**Notes on AC5.2 (Partial):** Phase 3 tests verify the data loader's cursor-based pagination (second page returns correct rows, no duplicates, no gaps). The infinite scroll UI behaviour and correct DOM insertion into section containers is a Phase 7 concern verified via E2E. AC5.5 uses the Phase 2 load-test data with a presence guard (skipped if data absent).

### AC6: Navigation chrome

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC6.1 | Home icon on annotation tab bar navigates to `/` | E2E | `tests/e2e/test_navigator.py` | Phase 8 / Task 4 | Planned |
| AC6.2 | Home icon on roleplay and courses pages navigates to `/` | E2E | `tests/e2e/test_navigator.py` | Phase 8 / Task 4 | Planned |
| AC6.3 | No global header bar imposed on annotation page | E2E | `tests/e2e/test_navigator.py` | Phase 8 / Task 4 | Planned |

### AC7: i18n terminology

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC7.1 | All user-facing text displays "Unit" not "Course" | E2E | `tests/e2e/test_navigator.py` | Phase 8 / Task 5 | Planned |
| AC7.2 | Label is configurable via pydantic-settings, defaults to "Unit" | Unit + Integration | `tests/unit/test_config.py` or `tests/integration/test_navigator_loader.py` | Phase 8 / Task 5 | Planned |

**Notes on AC7.1:** Already satisfied in the codebase (previous rename). Phase 8 E2E test verifies no regression by checking rendered page text does not contain "Course". AC7.2 is tested as a unit test on the config model (verify default value) and optionally with an environment variable override.

### AC8: FTS infrastructure

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC8.1 | `workspace_document` has GIN index on tsvector expression | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 1 | Covered |
| AC8.2 | HTML tags stripped from indexed content | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Covered |
| AC8.3 | `ts_headline` returns snippet with highlighted terms | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Covered |
| AC8.4 | Short queries (<3 chars) do not trigger FTS | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Covered |
| AC8.4 | (UI behaviour) Typing <3 chars does not trigger server-side search | E2E | `tests/e2e/test_navigator.py` | Phase 5 / Task 4 | Planned |
| AC8.5 | Empty document content produces valid tsvector, no errors | Integration + Unit | `tests/integration/test_fts_search.py`, `tests/unit/test_search_extraction.py` | Phase 1 / Tasks 3, 6 | Covered |

**Notes on AC8.1:** The design plan specified a generated tsvector column. Phase 1 implements a GIN expression index instead (PostgreSQL `to_tsvector()` is not immutable, so cannot be used in `GENERATED ALWAYS AS STORED`). The integration test verifies the expression index exists and FTS queries use it, which achieves equivalent acceptance.

**Notes on AC8.4:** Phase 1 covers the query helper's guard (raises/returns empty for <3 char queries). Phase 5 E2E test verifies the UI does not trigger search for short inputs (type 2 chars, wait, confirm no filtering occurs).

---

## Human Verification

| AC ID | Description | Verification Approach | Phase | Status |
|-------|-------------|----------------------|-------|--------|
| AC1.4 | Anonymised student names in "Shared in [Unit]" | Visually verify student section shows pseudonyms, not real names. Compare with database `user.display_name` to confirm anonymisation applied. | Phase 4 | Pending |
| AC2.4 | Workspace entry shows `updated_at` as formatted date | Visually inspect workspace entries on the navigator. Verify each shows a human-readable date/relative time. Cross-check against database `workspace.updated_at`. | Phase 4 | Pending |
| AC2.5 | Unauthenticated user redirected to login | Open navigator URL in incognito browser. Verify redirect to Stytch login page, not navigator content. | Phase 4 | Pending |
| AC3.1 | Search debounce behaviour feels responsive | Type a search query. Verify results appear after a brief pause (not instant, not sluggish). Confirm no intermediate flickering. | Phase 5 | Pending |
| AC5.5 | 1100+ students renders without degradation | Run against Phase 2 load-test data. Scroll through instructor view of large unit. Verify: no UI freezing, infinite scroll works, page remains responsive. Measure initial load time (<2s target). | Phase 7 | Pending |
| AC6.3 | No global header bar on annotation page | Open an annotation workspace. Verify the annotation page layout is unchanged -- only a small home icon added to the tab bar, no new header bar or structural change. | Phase 8 | Pending |
| AC7.1 | "Unit" displayed everywhere (not "Course") | Visually inspect navigator sections, courses page, and other UI surfaces. Grep rendered HTML for the string "Course" in non-code contexts. Confirm no regressions. | Phase 8 | Pending |
| Phase 3 / Task 4 | Human review gate for navigator SQL query | Review `navigator.sql`, `EXPLAIN ANALYZE` results, and integration test results. Approve correctness, permission filtering, and query performance before Phase 4 proceeds. | Phase 3 / Task 4 | Covered |

---

## Phase-by-Phase Test Coverage

### Phase 1: FTS Infrastructure (Implemented)

**Acceptance criteria covered:** AC8.1, AC8.2, AC8.3, AC8.4, AC8.5 (fully); AC3.2, AC3.4 (partially -- query layer only).

**Test files:**
- `tests/integration/test_fts_search.py` -- FTS query helper, HTML stripping, snippet generation, short query guard, empty content handling
- `tests/unit/test_search_extraction.py` -- Content extraction unit tests

### Phase 2: Load-Test Data (Implemented)

**Acceptance criteria covered:** None directly. Provides infrastructure for Phase 3 scale testing (AC5.5) and Phase 7 E2E scale verification.

### Phase 3: Navigator SQL Query (Implemented)

**Acceptance criteria covered:** AC1.1-AC1.8 (data layer); AC5.1, AC5.3, AC5.4, AC5.5 (data layer); AC5.2 (partial -- cursor pagination logic, not UI); AC2.4 (partial -- `updated_at` in query output).

**Test files:**
- `tests/integration/test_navigator_loader.py` -- All four sections, permission filtering, cursor pagination, multi-unit enrolment, loose workspaces, empty sections, 1100+ student scale

### Phase 4: Navigator Page Core (Planned)

**Acceptance criteria covered:** AC1.1-AC1.8 (UI rendering); AC2.1, AC2.2, AC2.3, AC2.5 (navigation); AC5.1, AC5.4 (initial load rendering).

**Planned test files:**
- `tests/e2e/test_navigator.py` -- Phase 4 Tasks 4-5:
  - Unauthenticated redirect to login (AC2.5)
  - My Work section renders with workspace entries (AC1.1)
  - Unstarted Work section visible (AC1.2)
  - Empty sections not rendered (AC1.7)
  - Title click navigates to annotation page (AC2.1)
  - Start button clones and navigates (AC2.3)
  - After Start, activity moves from Unstarted to My Work

### Phase 5: Search (Planned)

**Acceptance criteria covered:** AC3.1 (deviation -- server-side filter), AC3.2, AC3.4, AC3.5, AC3.6 (search UI); AC8.4 (UI-level short query guard).

**Planned test files:**
- `tests/e2e/test_navigator.py` -- Phase 5 Task 4:
  - Type 3+ chars matching document content, wait for debounce, verify filtered results with snippet (AC3.2, AC3.4)
  - Clear search input, verify full view restores (AC3.5)
  - Search for non-existent term, verify "No workspaces match" with clear option (AC3.6)
  - Type only 2 chars, wait 1 second, verify no filtering occurs (AC8.4)

### Phase 6: Inline Title Rename (Planned)

**Acceptance criteria covered:** AC4.1-AC4.5 (inline title editing and default title on clone).

**Planned test files:**
- `src/promptgrimoire/db/workspaces.py` modification -- Phase 6 Task 1: `clone_workspace_from_activity()` sets `title=activity.title`
- Existing integration tests updated to expect `title=activity.title` instead of `title=None` (Phase 6 Task 1)
- `tests/e2e/test_navigator.py` -- Phase 6 Tasks 3-4:
  - Click pencil icon, verify input becomes editable (AC4.1)
  - Type new title, press Enter, verify title updates and persists after refresh (AC4.2)
  - Click pencil, type title, click elsewhere (blur), verify title saves (AC4.2)
  - Click pencil, type title, press Escape, verify title reverts (AC4.3)
  - Click pencil, verify URL does not change; click title text, verify navigation (AC4.5)
  - Start activity, navigate back, verify workspace title matches activity name (AC4.4)

### Phase 7: Cursor Pagination UI (Planned)

**Acceptance criteria covered:** AC5.1-AC5.5 (infinite scroll UI behaviour).

**Planned test files:**
- `tests/e2e/test_navigator.py` -- Phase 7 Tasks 3-4:
  - Set up 60+ rows, verify initial ~50 rows visible, scroll to bottom, verify more rows load (AC5.1, AC5.2)
  - Set up <50 rows, verify all visible, scroll to bottom, verify no additional loading (AC5.4)
  - Verify infinite scroll works through multiple page loads without duplicates (AC5.5)
  - Type search query, scroll to bottom of results, verify no additional rows loaded; clear search, verify pagination resumes (AC5.2 interaction)

### Phase 8: Navigation Chrome & i18n (Planned)

**Acceptance criteria covered:** AC6.1-AC6.3 (home icon navigation); AC7.1-AC7.2 (i18n terminology).

**Planned test files:**
- `tests/e2e/test_navigator.py` (or `tests/e2e/test_navigation_chrome.py`) -- Phase 8 Tasks 4-5:
  - Navigate to annotation page, click home icon, verify URL changes to `/` (AC6.1)
  - Navigate to `/roleplay`, click home icon, verify navigation to `/`; repeat for `/courses` (AC6.2)
  - Verify annotation page has no global header bar, only small home icon button (AC6.3)
  - Navigate to `/`, verify no text contains "Course" (AC7.1)
- `tests/unit/test_config.py` or `tests/integration/` -- Phase 8 Task 5:
  - Verify `get_settings().i18n.unit_label` returns `"Unit"` by default (AC7.2)
  - Optionally verify environment variable override changes the value (AC7.2)

---

## Summary

| Category | Count |
|----------|-------|
| Acceptance criteria (total, excluding removed AC3.3) | 34 |
| Fully covered by Phases 1-3 automated tests (data layer) | 16 |
| Partially covered by Phases 1-3 automated tests | 4 |
| Planned for Phases 4-8 automated tests | 14 |
| Requiring human verification (in addition to automated tests) | 8 |

**Phase 1 covers:** AC8 (FTS infrastructure) fully, AC3.2 and AC3.4 partially (query layer only).

**Phase 2 covers:** No ACs directly (infrastructure for Phase 3 scale testing).

**Phase 3 covers:** AC1 (all sections) fully at the data layer, AC5 (pagination) at the data layer. AC1.4 is partial because anonymisation is a rendering concern.

**Phase 4 covers:** AC1 (UI rendering), AC2 (navigation, clone, auth redirect), AC5.1/AC5.4 (initial load rendering).

**Phase 5 covers:** AC3 (search UI -- filtering, snippets, clear, no-results), AC8.4 (UI-level short query guard).

**Phase 6 covers:** AC4 (inline rename -- pencil icon, save/cancel, default title on clone).

**Phase 7 covers:** AC5 (infinite scroll -- load more, correct section placement, search interaction, scale).

**Phase 8 covers:** AC6 (home icon on annotation, roleplay, courses), AC7 (configurable unit label, no "Course" in UI).
