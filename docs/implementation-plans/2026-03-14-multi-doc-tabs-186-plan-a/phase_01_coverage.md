# Phase 1: Characterisation Test Coverage

**Purpose:** Reference for Phases 2-6 to know what regression safety exists before modifying card rendering, tab management, and document handling.

**Date:** 2026-03-14

---

## Coverage by Tab

### Annotate Tab (cards.py)

| Behaviour | Test File | Status |
|-----------|-----------|--------|
| Card rendered per highlight | `tests/e2e/test_card_layout.py::TestCollapsedCards::test_default_collapsed_with_compact_header` | Existing |
| Cards ordered by `start_char` (non-overlapping positions) | `tests/e2e/test_card_layout.py::TestCardPositioning::test_initial_positioning_non_zero_no_overlap` | Existing |
| Expandable text toggle (expand/collapse) | `tests/e2e/test_card_layout.py::TestCollapsedCards::test_expand_collapse_toggle` | Existing |
| Default collapsed with compact header | `tests/e2e/test_card_layout.py::TestCollapsedCards::test_default_collapsed_with_compact_header` | Existing |
| Author initials in compact header | `tests/e2e/test_card_layout.py::TestCollapsedCards::test_author_initials_in_compact_header` | Existing |
| Push-down on expand | `tests/e2e/test_card_layout.py::TestCollapsedCards::test_push_down_on_expand` | Existing |
| Viewer sees no tag-select or comment-input | `tests/e2e/test_card_layout.py::TestCollapsedCards::test_viewer_sees_no_tag_select_or_comment_input` | Existing |
| Scroll recovery (no solitaire collapse) | `tests/e2e/test_card_layout.py::TestCardPositioning::test_scroll_recovery_no_solitaire_collapse` | Existing |
| SPA navigation race condition | `tests/e2e/test_card_layout.py::TestCardPositioning::test_race_condition_highlights_ready` | Existing |
| Comment posting via card UI | `tests/e2e/test_annotation_canvas.py::test_instructor_marking_interactions` | Existing |
| `_author_initials(name)` pure function | `tests/unit/test_card_functions.py` | New (Task 1) |
| `anonymise_author()` rules | `tests/unit/test_card_functions.py` | New (Task 1) |
| `_build_expandable_text` 80-char threshold (exact boundary pinned) | `tests/integration/test_annotation_cards_charac.py` | New (Task 3) |
| `cards_epoch` / `window.__annotationCardsEpoch` | Not testable in NiceGUI User harness (no real browser). Deferred to Phase 5 E2E tests | Gap |
| Tag name on card header | Not directly tested — cards render with tag context but no assertion on tag label text | Gap |
| Comment count badge | `tests/integration/test_annotation_cards_charac.py` | New (Task 3) |
| Locate button on card | `tests/integration/test_annotation_cards_charac.py` | New (Task 3) |

### Organise Tab (organise.py)

| Behaviour | Test File | Status |
|-----------|-----------|--------|
| Cards grouped by tag column | `tests/e2e/test_law_student.py` (organise_highlight_in_correct_column) | Existing |
| Card shows author and text | `tests/e2e/test_law_student.py` (organise_card_shows_author_and_text) | Existing |
| Locate button warps to Annotate | `tests/e2e/test_law_student.py` (organise_locate_warps_to_annotate) | Existing |
| No untagged column when all tagged | `tests/e2e/test_law_student.py` (no_untagged_column_in_organise) | Existing |
| Comments rendered on organise card | `tests/e2e/test_annotation_canvas.py::test_instructor_marking_interactions` | Existing |
| Cross-tab sync (new card appears for peer) | `tests/e2e/test_history_tutorial.py` (cross_tab_organise_sync) | Existing |
| Drag-to-retag | `tests/e2e/test_annotation_drag.py` | Existing |
| Performance with 10 highlights | `tests/e2e/test_organise_perf.py` | Existing |
| Highlight text visible after cross-tab nav | `tests/e2e/test_organise_respond_flow.py::test_highlight_appears_across_all_three_tabs` | New (Task 6) |
| Snippet truncated at 100 chars | `tests/integration/test_organise_charac.py` | New (Task 4) |
| Full text shown for short snippets | `tests/integration/test_organise_charac.py` | New (Task 4) |
| `anonymise_author()` called (cross-user with anonymous_sharing=True) | `tests/integration/test_organise_charac.py` | New (Codex audit fix) |

### Respond Tab (respond.py)

| Behaviour | Test File | Status |
|-----------|-----------|--------|
| Reference panel visible with tag groups | `tests/e2e/test_law_student.py` (respond_reference_panel) | Existing |
| Reference card count matches highlights | `tests/e2e/test_law_student.py` (respond_reference_panel) | Existing |
| Locate button warps to Annotate | `tests/e2e/test_law_student.py` (respond_locate_warps_to_annotate) | Existing |
| Empty state message ("No highlights yet") | `tests/e2e/test_law_student.py` (respond_tab_empty_state) | Existing |
| Cross-tab sync (new ref card appears) | `tests/e2e/test_history_tutorial.py` (cross_tab_respond_sync) | Existing |
| Comment text visible on reference card | `tests/e2e/test_organise_respond_flow.py::test_comment_visible_on_respond_tab` | New (Task 6) |
| Highlight text visible on reference card | `tests/e2e/test_organise_respond_flow.py::test_highlight_appears_across_all_three_tabs` | New (Task 6) |
| Snippet truncated at 100 chars | `tests/integration/test_respond_charac.py` | New (Task 5) |
| **Raw author displayed to viewer with anonymous_sharing=True (known bug)** | `tests/integration/test_respond_charac.py` | New (Codex audit fix) |

### Cross-Tab Flows

| Behaviour | Test File | Status |
|-----------|-----------|--------|
| Highlight -> Annotate card -> Organise card -> Respond ref card | `tests/e2e/test_law_student.py` | Existing |
| Comment on Annotate -> visible on Organise | `tests/e2e/test_annotation_canvas.py` | Existing |
| Comment on Annotate -> visible on Respond | `tests/e2e/test_organise_respond_flow.py` | New (Task 6) |
| Cross-tab highlight text visibility (smoke test, not full consistency) | `tests/e2e/test_organise_respond_flow.py` | New (Task 6) |

### Pure Functions

| Function | Test File | Status |
|----------|-----------|--------|
| `group_highlights_by_tag()` | `tests/unit/test_card_functions.py` | New (Task 1) |
| `_author_initials()` | `tests/unit/test_card_functions.py` | New (Task 1) |
| `anonymise_author()` | `tests/unit/test_card_functions.py` | New (Task 1) |
| `get_highlights_for_document()` filtering | `tests/unit/test_annotation_doc.py` | New (Task 2) |

---

## Known Gaps and Bugs

### 1. `anonymise_author` missing from respond.py

**Bug:** `respond.py` displays raw author names instead of calling `anonymise_author()`. The characterisation test `test_respond_shows_raw_author_to_viewer` locks in this broken behaviour with `anonymous_sharing=True` on the Activity and a second viewer user — so when Phase 2 adds `anonymise_author()` to respond.py, the viewer will see a pseudonym and the test will fail, requiring update.

### 2. Snippet truncation inconsistency

Current values:
- **cards.py** (Annotate tab): 80-char expandable text with expand/collapse toggle (`_build_expandable_text`)
- **organise.py** (Organise tab): 100-char static truncation with "..." suffix (`_SNIPPET_MAX_CHARS = 100`)
- **respond.py** (Respond tab): 100-char static truncation with "..." suffix (`_SNIPPET_MAX_CHARS = 100`)

Phase 2 will unify Organise and Respond to use the same 80-char expandable text widget from cards.py.

### 3. Tests expected to change in Phase 2

| Test | Current Behaviour | Phase 2 Change |
|------|-------------------|----------------|
| `test_organise_charac.py` | 100-char static truncation | 80-char expandable text |
| `test_respond_charac.py` | 100-char static truncation | 80-char expandable text |
| `test_respond_charac.py` | Displays raw author name | Displays anonymised author |

---

## Technical Debt Flagged by Phase 1

### DB setup helper chain duplicated across integration test files

`_create_course`, `_enroll`, `_create_week`, `_create_activity`,
`_setup_template_tags`, `_add_template_document`, `_clone_workspace`,
`_add_highlights_to_workspace`, and `_setup_workspace_with_highlights` are
near-identical in all three integration test files:

- `tests/integration/test_annotation_cards_charac.py`
- `tests/integration/test_organise_charac.py`
- `tests/integration/test_respond_charac.py`

They differ only in course-code prefix (`ANN`, `ORG`, `RSP`) and test-specific
highlight content. Extract these into a shared
`tests/integration/annotation_fixtures.py` module during Phase 3 or as a
standalone cleanup task. The course-code prefix can be passed as a parameter.

**Scope:** Phase 3 cleanup task or dedicated refactor. Not urgent — tests are
correct, the duplication is cosmetic.

---

## Coverage Gaps Not Addressed by Phase 1

These behaviours are not tested and are out of scope for Phase 1 characterisation:

1. **Multi-document filtering** -- highlights from different `document_id` values are not tested in E2E (only unit tests planned in Task 2). This becomes relevant in Phase 7 when multi-document tabs are introduced.
2. **Concurrent editing card updates** -- covered partially by `test_history_tutorial.py` but not exhaustively. Phase 5 (diff-based updates) will need its own tests.
3. **Copy protection interaction with cards** -- not tested (separate feature, not affected by card refactoring).
4. **PDF export of card content** -- covered by `test_law_student.py` and `test_translation_student.py` but not as characterisation tests.
