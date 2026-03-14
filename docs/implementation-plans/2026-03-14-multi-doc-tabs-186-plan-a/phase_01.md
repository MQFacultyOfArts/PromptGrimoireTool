# Multi-Document Tabbed Workspace Implementation Plan (Plan A)

**Goal:** Refactor card rendering and tab management to prepare for multi-document support — card consistency fixes, shared utility extraction, diff-based updates, tab management extraction, and multi-document tab infrastructure.

**Architecture:** Phases 1–3b clean up and extract shared card rendering code across the Annotate, Organise, and Respond tabs. Phase 4 replaces the clear-and-rebuild card update with surgical diff-based operations. Phase 5 extracts tab management from the 866-line `workspace.py`. Phase 6 wires up the multi-document tab bar. The CRDT layer already stores `document_id` on highlights — the gap is UI only.

**Tech Stack:** Python 3.14, NiceGUI, pycrdt, PostgreSQL, pytest, Playwright

**Scope:** 7 phases from original design (phases 1–6 including 3b). This is Plan A of two implementation plans.

**After Plan A execution:**
1. Code review → UAT
2. Update `docs/annotation-architecture.md` for new module structure (card_shared.py, tab_bar.py, tab_state.py)
3. Review `docs/architecture/dfd/5-annotate-texts.md` — note any data flow changes needed (most changes are Plan B scope)
4. Invoke `/denubis-plan-and-execute:starting-an-implementation-plan` for Plan B (design phases 7–13) on the same branch
5. Plan B execution → code review → UAT
6. Update Level 2 DFD for annotation (new data flows: document add/rename/delete, cross-tab locate, cross-client sync)
7. PR/merge — the full feature lands in one PR

**Codebase verified:** 2026-03-14

### Design-to-Implementation Phase Mapping

| Impl Phase | Design Phase | Name |
|-----------|-------------|------|
| Phase 1 | Phase 1 | Characterisation Tests for Card Behaviour |
| Phase 2 | Phase 2 | Card Consistency Fixes |
| Phase 3 | Phase 3 | Extract Shared Utilities from cards.py |
| Phase 4 | Phase 3b | Extract Shared Utilities from respond.py |
| Phase 5 | Phase 4 | Diff-Based Card Updates |
| Phase 6 | Phase 5 | Extract Tab Management from workspace.py |
| Phase 7 | Phase 6 | Multi-Document Tab Infrastructure |

---

## Phase 1: Characterisation Tests for Card Behaviour

### Acceptance Criteria Coverage

This phase establishes a regression safety net — no ACs are directly verified. The tests lock down existing behaviour before Phases 2–6 modify it. They protect against regressions for:

- multi-doc-tabs-186.AC11 (Card Consistency) — tests will detect if refactoring breaks expandable text or anonymisation
- multi-doc-tabs-186.AC12 (Diff-Based Card Updates) — tests will detect if card ordering or content changes during diff migration

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Unit tests for pure card data functions

**Verifies:** None (characterisation — locks down existing behaviour)

**Files:**
- Test: `tests/unit/test_card_functions.py` (unit)

**Implementation:**
Unit tests for pure functions that can be tested without NiceGUI or database:

- `respond.py:68` `group_highlights_by_tag(tags, crdt_doc)` — groups highlights by tag, returns dict. Test with: multiple tags, highlight in multiple tags, highlight with no tag, empty input.
- `cards.py:34` `_author_initials(name)` — derives compact initials from display name. Test with: "Alice Smith" → "AS", single name, empty string, None.
- `auth/__init__.py` `anonymise_author()` — verify anonymisation rules. Test with: own-user vs other-user, privileged vs non-privileged.

**Testing:**
Tests exercise each function's edge cases. These are pure functions — no mocking needed.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_card_functions.py`
Expected: All tests pass

**Commit:** `test: add unit tests for card data functions (characterisation)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for CRDT highlight filtering

**Verifies:** None (characterisation — locks down existing behaviour)

**Files:**
- Test: `tests/unit/test_annotation_doc.py` (extend existing, unit)

**Implementation:**
Add tests to the existing `test_annotation_doc.py` that characterise `get_highlights_for_document()` behaviour:

- Highlights filtered by `document_id` — only matching highlights returned
- Highlights ordered by `start_char` within a document
- Highlights from different documents don't cross-contaminate
- Empty document returns empty list

Check existing tests first — some may already cover this. Only add what's missing.

**Testing:**
Tests use `AnnotationDoc` directly (no DB, no NiceGUI). Create doc, add highlights with different `document_id` values, verify filtering.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_annotation_doc.py`
Expected: All tests pass (existing + new)

**Commit:** `test: characterise get_highlights_for_document filtering and ordering`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: NiceGUI integration tests for Annotate tab card rendering

**Verifies:** None (characterisation — locks down existing behaviour)

**Files:**
- Test: `tests/integration/test_annotation_cards_charac.py` (integration, `@pytest.mark.nicegui_ui`)
- Reference: `tests/integration/nicegui_helpers.py` — `_should_see_testid()`, `_find_by_testid()`
- Reference: `tests/integration/conftest.py` — `nicegui_user` fixture, `_authenticate()`
- Reference: `tests/integration/test_crud_management_ui.py` — example NiceGUI integration test pattern
- Reference: `docs/testing.md` — testing guidelines

**Implementation:**
NiceGUI integration tests that verify card rendering in the Annotate tab (cards.py).

Setup pattern (per test or fixture):
1. Create workspace + document in DB via factory fixtures
2. Add highlights to CRDT with known `start_char`, tags, and comments
3. Navigate NiceGUI user to annotation page
4. Assert rendered elements

Tests to write:
- Cards rendered for each highlight (one card per highlight, `data-testid="annotation-card"`)
- Cards ordered by `start_char` (first highlight has lowest `start_char`)
- Expandable text present — truncated text visible, full text hidden (80-char threshold in `_build_expandable_text`)
- Tag name displayed on card header
- Comment count badge visible when comments exist
- Author initials displayed (anonymised via `anonymise_author`)
- Locate button present on each card (`icon="my_location"`)
- `cards_epoch` incremented after card rendering

Follow the existing pattern in `test_crud_management_ui.py` — use `@pytest.mark.asyncio`, `@pytest.mark.nicegui_ui`, `nicegui_user` fixture.

**Testing:**
Each test asserts specific rendering properties. Use `_should_see_testid()` and `_find_by_testid()` from `nicegui_helpers.py`. If a testid doesn't exist on the element, add `data-testid` to the production code (noting it in the test).

**Verification:**
Run: `uv run grimoire test run tests/integration/test_annotation_cards_charac.py`
Expected: All tests pass against unmodified card rendering code

**Commit:** `test: add characterisation tests for Annotate tab card rendering`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: NiceGUI integration tests for Organise tab rendering

**Verifies:** None (characterisation — locks down existing behaviour)

**Files:**
- Test: `tests/integration/test_organise_charac.py` (integration, `@pytest.mark.nicegui_ui`)
- Reference: same helpers as Task 3

**Implementation:**
NiceGUI integration tests for Organise tab (organise.py) card rendering.

Tests to write:
- Organise cards rendered (`data-testid="organise-card"`)
- Snippet text truncated at 100 chars (`_SNIPPET_MAX_CHARS = 100`) with "..." suffix
- Full text shown for snippets under 100 chars (no "..." suffix)
- Locate button present (`icon="my_location"`)
- Author display uses `anonymise_author()` (confirmed present in organise.py)
- Comment text visible on cards
- Cards grouped by tag

**Testing:**
Create CRDT state with highlights that have: text >100 chars, text <100 chars, comments, tags. Navigate to Organise tab. Assert rendered elements match expectations.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_organise_charac.py`
Expected: All tests pass

**Commit:** `test: add characterisation tests for Organise tab rendering`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: NiceGUI integration tests for Respond tab rendering

**Verifies:** None (characterisation — locks down existing behaviour)

**Files:**
- Test: `tests/integration/test_respond_charac.py` (integration, `@pytest.mark.nicegui_ui`)
- Reference: same helpers as Task 3

**Implementation:**
NiceGUI integration tests for Respond tab (respond.py) reference card rendering.

Tests to write:
- Reference cards rendered (`data-testid="respond-reference-card"`)
- Snippet text truncated at 100 chars with "..." suffix
- Locate button present
- Comment text visible
- **Document the anonymisation gap**: test that respond.py does NOT anonymise authors (raw author string displayed). This is the known bug — the characterisation test locks in current (broken) behaviour so Phase 2 can fix it and we see the test change.

**Testing:**
Create CRDT state with highlights, tags, and comments. Navigate to Respond tab. Assert rendered elements. The "non-anonymised author" test should assert the raw author name is displayed — this test will need updating in Phase 2 when `anonymise_author()` is added.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_respond_charac.py`
Expected: All tests pass (including the "displays raw author" characterisation test)

**Commit:** `test: add characterisation tests for Respond tab rendering`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Review and extend E2E card flow tests

**Verifies:** None (characterisation — verifies existing flows work end-to-end)

**Files:**
- Modify: `tests/e2e/test_card_layout.py` — review existing tests, add gaps
- Test: `tests/e2e/test_organise_respond_flow.py` (e2e, new if needed)
- Reference: `tests/e2e/card_helpers.py` — `expand_card()`, `collapse_card()`, `add_comment_to_highlight()`
- Reference: `tests/e2e/highlight_tools.py` — `create_highlight()`, `find_text_range()`

**Implementation:**
Review existing E2E tests (`test_card_layout.py`, `test_edit_mode.py`) and identify gaps in flow coverage. The existing tests cover card positioning and edit mode — extend to cover:

- Highlight creation → card appears in sidebar → card appears in Organise tab → card appears in Respond tab (cross-tab flow)
- Comment added on Annotate tab → visible on Organise and Respond tabs
- Expandable text toggle works (click expand, verify full text visible; click collapse, verify truncated)

Only add tests that aren't already covered. Check existing test files first.

**Testing:**
Follow existing E2E patterns. Use `page.get_by_test_id()` locators, epoch synchronisation for card rebuilds, `card_helpers.py` and `highlight_tools.py` utilities.

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: All existing + new E2E card tests pass

**Commit:** `test: extend E2E card flow tests for cross-tab characterisation`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Document test coverage gaps

**Verifies:** None (documentation only)

**Files:**
- Create: `docs/implementation-plans/2026-03-14-multi-doc-tabs-186-plan-a/phase_01_coverage.md`

**Implementation:**
After all characterisation tests pass, document:

1. What card rendering behaviours are now covered by tests (by tab)
2. What gaps remain (if any) — interactions not tested, edge cases not covered
3. Current `anonymise_author` gap in respond.py (to be fixed in Phase 2)
4. Current snippet truncation values: 80 chars (cards.py expandable text), 100 chars (organise/respond snippet)

This document serves as the reference for Phases 2–6 to know what regression safety exists.

**Tests expected to change in Phase 2:**
- `test_organise_charac.py`: 100-char static truncation → 80-char expandable text
- `test_respond_charac.py`: 100-char static truncation → 80-char expandable text
- `test_respond_charac.py`: "displays raw author" → "displays anonymised author" (bug fix)

**Verification:**
Run: `uv run grimoire test all` — all unit + integration tests pass
Run: `uv run grimoire e2e cards` — all card E2E tests pass

**Commit:** `docs: document Phase 1 characterisation test coverage`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->
