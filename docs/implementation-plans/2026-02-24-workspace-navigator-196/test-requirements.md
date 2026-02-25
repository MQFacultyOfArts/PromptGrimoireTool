# Workspace Navigator -- Test Requirements

## Scope

This document maps every acceptance criterion from the [design plan](../../design-plans/2026-02-24-workspace-navigator-196.md) to either automated tests or human verification procedures.

**Phases covered by implementation plans:** Phases 1-3 only.

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | FTS infrastructure (indexes, extraction, query helper, worker) | Planned |
| Phase 2 | Load-test fixture (1100-student dataset) | Planned |
| Phase 3 | Navigator SQL query (UNION ALL data loader, integration tests) | Planned |
| Phase 4 | Search (client-side filter + FTS UI wiring) | Not yet planned |
| Phase 5 | Inline title rename | Not yet planned |
| Phase 6 | Cursor pagination (UI "Load more" interaction) | Not yet planned |
| Phase 7 | Navigation chrome and i18n | Not yet planned |

Phases 4-7 are referenced where acceptance criteria depend on them. Any criterion marked "Deferred" has no planned test coverage yet and will need test specifications when those phases are written.

---

## Automated Test Matrix

### AC1: Navigator page renders all sections

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC1.1 | Student sees "My Work" with owned workspaces grouped by unit > week > activity | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.2 | Student sees "Unstarted Work" with published activities not yet started | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.3 | Student sees "Shared With Me" with editor/viewer ACL workspaces | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.4 | Student sees "Shared in [Unit]" with peer workspaces grouped by anonymised student | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Partial |
| AC1.5 | Instructor sees "Shared in [Unit]" with all student workspaces by real student name | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.6 | Loose workspaces (no activity) appear under "Unsorted" in student grouping | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.7 | Empty sections hidden (produce zero rows) | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC1.8 | Multi-enrolled student sees separate "Shared in [Unit]" per unit | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |

**Notes on AC1.4 (Partial):** Phase 3 tests verify the raw query returns correct rows with `owner_display_name` for the peer section. Anonymisation is applied at the rendering layer (Python, not SQL), so the integration test verifies data correctness but not the anonymised display. Full verification requires either a unit test on the anonymisation call in the page renderer (Phase 4+) or E2E verification.

### AC2: Workspace navigation

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC2.1 | Title click navigates to `/annotation?workspace_id=<uuid>` | E2E | TBD | Phase 4+ | Deferred |
| AC2.2 | Action button (Resume/Open/View) navigates to workspace | E2E | TBD | Phase 4+ | Deferred |
| AC2.3 | [Start] on unstarted activity clones template and navigates | E2E | TBD | Phase 4+ | Deferred |
| AC2.4 | Each workspace entry shows `updated_at` | E2E | TBD | Phase 4+ | Deferred |
| AC2.5 | Unauthenticated user redirected to login | E2E | TBD | Phase 4+ | Deferred |

**Note:** AC2.4 is partially covered by Phase 3 integration tests, which verify that `updated_at` is present in the query output columns. The visual rendering of the date is a UI concern for Phase 4+.

### AC3: Search

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC3.1 | Client-side filter by title/unit/activity/student name on every keystroke | E2E | TBD | Phase 4 | Deferred |
| AC3.2 | FTS fires at >=3 chars with debounce, surfaces content matches with snippet | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Partial |
| AC3.3 | Instructor search matches student display names | E2E | TBD | Phase 4 | Deferred |
| AC3.4 | FTS results show content snippet explaining the match | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Partial |
| AC3.5 | Clearing search restores full unfiltered list | E2E | TBD | Phase 4 | Deferred |
| AC3.6 | No results shows "No workspaces match" with clear option | E2E | TBD | Phase 4 | Deferred |

**Notes on AC3.2 and AC3.4 (Partial):** Phase 1 / Task 6 tests verify the FTS query helper returns correct results with `ts_headline` snippets. The debounce trigger logic, UI wiring, and display of snippet beneath workspace cards are Phase 4 concerns. AC3.3 (instructor name search) requires the navigator page to pass student names into the search context, which is a Phase 4 integration concern.

### AC4: Inline title rename

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC4.1 | Pencil icon activates inline edit | E2E | TBD | Phase 5 | Deferred |
| AC4.2 | Enter or blur saves new title | E2E | TBD | Phase 5 | Deferred |
| AC4.3 | Escape cancels edit without saving | E2E | TBD | Phase 5 | Deferred |
| AC4.4 | New workspaces default title to activity name | Integration | TBD | Phase 5 | Deferred |
| AC4.5 | Pencil click does not navigate (only title click navigates) | E2E | TBD | Phase 5 | Deferred |

**Note:** AC4.4 could be covered by a unit or integration test on the clone function once the default-title logic is implemented.

### AC5: Cursor pagination

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC5.1 | Initial load shows first 50 rows | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.2 | "Load more" fetches next 50, appended into correct sections | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Partial |
| AC5.3 | Students with no workspaces (instructor view) appear at end of unit section | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.4 | Fewer than 50 rows -- all returned, no "Load more" | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |
| AC5.5 | Works correctly with 1100+ students | Integration | `tests/integration/test_navigator_loader.py` | Phase 3 / Task 3 | Covered |

**Notes on AC5.2 (Partial):** Phase 3 tests verify the data loader's cursor-based pagination (second page returns correct rows, no duplicates, no gaps). The UI "Load more" button behaviour and correct DOM insertion into section containers is a Phase 6 concern requiring E2E tests. AC5.3 is listed in the Phase 3 / Task 3 additional test cases (instructor view zero-workspace students). AC5.5 uses the Phase 2 load-test data with a presence guard (skipped if data absent).

### AC6: Navigation chrome

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC6.1 | Home icon on annotation tab bar navigates to `/` | E2E | TBD | Phase 7 | Deferred |
| AC6.2 | Home icon on roleplay and courses pages navigates to `/` | E2E | TBD | Phase 7 | Deferred |
| AC6.3 | No global header bar imposed on annotation page | E2E | TBD | Phase 7 | Deferred |

### AC7: i18n terminology

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC7.1 | All user-facing text displays "Unit" not "Course" | E2E | TBD | Phase 7 | Deferred |
| AC7.2 | Label is configurable via pydantic-settings, defaults to "Unit" | Unit | TBD | Phase 7 | Deferred |

**Note:** AC7.2 is well suited for a unit test on the config model (verify default value and override). AC7.1 requires E2E or manual visual inspection.

### AC8: FTS infrastructure

| AC ID | Description | Test Type | Test File | Phase/Task | Status |
|-------|-------------|-----------|-----------|------------|--------|
| AC8.1 | `workspace_document` has GIN index on tsvector expression | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 1 | Covered |
| AC8.2 | HTML tags stripped from indexed content | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Covered |
| AC8.3 | `ts_headline` returns snippet with highlighted terms | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Covered |
| AC8.4 | Short queries (<3 chars) do not trigger FTS | Integration | `tests/integration/test_fts_search.py` | Phase 1 / Task 6 | Covered |
| AC8.5 | Empty document content produces valid tsvector, no errors | Integration + Unit | `tests/integration/test_fts_search.py`, `tests/unit/test_search_extraction.py` | Phase 1 / Tasks 3, 6 | Covered |

**Notes on AC8.1:** The design plan specified a generated tsvector column. Phase 1 implements a GIN expression index instead (PostgreSQL `to_tsvector()` is not immutable, so cannot be used in `GENERATED ALWAYS AS STORED`). The integration test verifies that the expression index exists and FTS queries use it, which achieves equivalent acceptance.

---

## Human Verification

| AC ID | Description | Verification Approach | Phase | Status |
|-------|-------------|----------------------|-------|--------|
| AC1.4 | Anonymised student names in "Shared in [Unit]" | Visually verify student section shows pseudonyms, not real names. Compare with database `user.display_name` to confirm anonymisation applied. | Phase 4+ | Deferred |
| AC2.5 | Unauthenticated user redirected to login | Open navigator URL in incognito browser. Verify redirect to Stytch login page. | Phase 4+ | Deferred |
| AC5.5 | 1100+ students renders without degradation | Run against Phase 2 load-test data. Scroll through instructor view of LAWS1100. Verify: no UI freezing, "Load more" works, page remains responsive. Measure initial load time. | Phase 6 | Deferred |
| AC6.3 | No global header bar on annotation page | Open an annotation workspace. Verify the annotation page layout is unchanged -- only a small home icon added to the tab bar, no new header bar. | Phase 7 | Deferred |
| AC7.1 | "Unit" displayed everywhere (not "Course") | Visually inspect navigator sections, courses page, and any other UI surface. Grep rendered HTML for the string "Course" in non-code contexts. | Phase 7 | Deferred |
| Phase 3 / Task 4 | Human review gate for navigator SQL query | Review `navigator.sql`, `EXPLAIN ANALYZE` results, and integration test results. Approve correctness, permission filtering, and query performance before Phase 4 proceeds. | Phase 3 / Task 4 | Covered |

---

## Deferred to Future Phases

| AC ID | Description | Reason | Target Phase |
|-------|-------------|--------|--------------|
| AC2.1 | Title click navigates to workspace | Requires navigator page rendering (Phase 4+ UI) | Phase 4+ |
| AC2.2 | Action button navigates to workspace | Requires navigator page rendering | Phase 4+ |
| AC2.3 | [Start] clones template and navigates | Requires navigator page with clone wiring | Phase 4+ |
| AC2.4 | Workspace entry shows `updated_at` | Data available from Phase 3; display is Phase 4+ UI | Phase 4+ |
| AC2.5 | Unauthenticated redirect to login | Requires navigator page with auth guard | Phase 4+ |
| AC3.1 | Client-side filter on every keystroke | Client-side JS, requires navigator DOM | Phase 4 |
| AC3.3 | Instructor search matches student names | Requires FTS + navigator page integration | Phase 4 |
| AC3.5 | Clearing search restores full list | Client-side JS behaviour | Phase 4 |
| AC3.6 | No-results state with clear option | UI component | Phase 4 |
| AC4.1 | Pencil icon activates inline edit | New UI pattern, no precedent in codebase | Phase 5 |
| AC4.2 | Enter/blur saves title | Inline edit interaction | Phase 5 |
| AC4.3 | Escape cancels edit | Inline edit interaction | Phase 5 |
| AC4.4 | New workspace defaults title to activity name | Clone logic modification | Phase 5 |
| AC4.5 | Pencil click does not navigate | Event handling separation | Phase 5 |
| AC5.2 | UI "Load more" appends into correct sections | Data-layer pagination covered in Phase 3; UI append logic is Phase 6 | Phase 6 |
| AC5.3 | Zero-workspace students at end of unit section | Data ordering covered in Phase 3; visual rendering is Phase 6 | Phase 6 |
| AC6.1 | Home icon on annotation tab bar | Navigation chrome | Phase 7 |
| AC6.2 | Home icon on roleplay/courses pages | Navigation chrome | Phase 7 |
| AC6.3 | No global header imposed on annotation | Layout preservation | Phase 7 |
| AC7.1 | "Unit" displayed everywhere | i18n terminology | Phase 7 |
| AC7.2 | Configurable label via pydantic-settings | Configuration model | Phase 7 |

---

## Summary

| Category | Count |
|----------|-------|
| Acceptance criteria (total) | 36 |
| Fully covered by Phases 1-3 automated tests | 16 |
| Partially covered by Phases 1-3 automated tests | 4 |
| Deferred to Phases 4-7 | 16 |
| Requiring human verification (in addition to automated tests) | 6 |

**Phase 1 covers:** AC8 (FTS infrastructure) fully, AC3.2 and AC3.4 partially (query layer only).

**Phase 2 covers:** No ACs directly (infrastructure for Phase 3 scale testing).

**Phase 3 covers:** AC1 (all sections) fully at the data layer, AC5 (pagination) at the data layer. AC1.4 is partial because anonymisation is a rendering concern.

**Phases 4-7 (not yet planned)** are needed for: all AC2 (navigation), AC3.1/3.3/3.5/3.6 (search UI), all AC4 (inline rename), AC5 UI behaviour, all AC6 (chrome), and all AC7 (i18n).
