# Test Requirements -- Three-Tab Annotation Interface

## Overview

This document maps all 26 acceptance criteria from the three-tab-ui design to specific automated tests and human verification steps. Each AC is traced to the implementation phase that covers it, the test type (unit, integration, or E2E), the expected test file path, and the specific test name(s) from the phase plans.

Where automated tests cannot fully verify a criterion (visual layout, drag-feel, scroll smoothness), human verification is specified with a rationale.

---

## Automated Test Coverage

### three-tab-ui.AC1: Tab container wraps existing functionality

| AC | Type | Phase | Test File | Test Name(s) | Verification |
|----|------|-------|-----------|---------------|--------------|
| AC1.1 | E2E | Phase 1, Task 1 | `tests/e2e/test_annotation_tabs.py` | `test_tab_headers` | Asserts three tab elements exist with text "Annotate", "Organise", "Respond"; asserts "Annotate" is the active/selected tab on page load |
| AC1.2 | E2E | Phase 1, Task 3 | `tests/e2e/test_annotation_tabs.py` | (multi-client sync test) | Opens two browser contexts on same workspace, creates highlight in context 1, asserts it appears in context 2 -- verifies existing annotation functionality is unbroken by tab wrapping |
| AC1.3 | E2E | Phase 1, Task 2 | `tests/e2e/test_annotation_tabs.py` | `test_deferred_rendering` | Loads annotation page, checks Tab 2 panel contains placeholder text (not column layout), clicks "Organise" tab, verifies tab panel becomes visible |
| AC1.4 | E2E | Phase 1, Task 3 | `tests/e2e/test_annotation_tabs.py` | (state preservation test) | Creates a highlight in Tab 1, switches to Tab 2 then back to Tab 1, asserts highlight still exists (annotation card visible, highlight CSS present) and scroll position is preserved |

### three-tab-ui.AC2: Tab 2 organises highlights by tag

| AC | Type | Phase | Test File | Test Name(s) | Verification |
|----|------|-------|-----------|---------------|--------------|
| AC2.1 | Unit + E2E | Phase 3, Tasks 1-2 | `tests/unit/pages/test_annotation_tags.py`, `tests/e2e/test_annotation_tabs.py` | `test_brief_tags_to_tag_info_returns_all_tags`, `test_tag_info_names_are_title_case`, `test_tag_info_colours_are_hex`, `test_tag_info_colours_match_tag_colors`, `test_organise_tab_shows_tag_columns` | Unit tests verify TagInfo data structure correctness (10 entries, title-case names, valid hex colours). E2E test navigates to Organise tab, verifies tag column headers with correct names |
| AC2.2 | E2E | Phase 3, Task 2 | `tests/e2e/test_annotation_tabs.py` | `test_organise_tab_highlight_in_correct_column`, `test_organise_tab_card_shows_author_and_text` | Creates highlight with specific tag, switches to Organise tab, verifies card in correct column with author name and text snippet |
| AC2.3 | E2E | Phase 4, Task 3 | `tests/e2e/test_annotation_tabs.py` | `test_drag_reorder_within_column` | Creates two highlights with same tag, switches to Organise tab, uses Playwright `drag_to()` to reorder, switches tabs and back to verify order persists |
| AC2.4 | E2E | Phase 4, Task 3 | `tests/e2e/test_annotation_tabs.py` | `test_drag_between_columns_changes_tag`, `test_drag_between_columns_updates_tab1_sidebar` | Drags card from tag A column to tag B column, verifies card now in tag B column and Tag B shown on Tab 1 sidebar card. Multi-client variant verifies Tab 1 sidebar update on other client |
| AC2.5 | E2E | Phase 4, Task 3 | `tests/e2e/test_annotation_tabs.py` | `test_concurrent_drag_produces_consistent_result` | Two browser contexts on Tab 2 drag different highlights to different columns simultaneously; verifies both operations complete and both contexts show consistent final state |
| AC2.6 | E2E | Phase 3, Task 2 (creation); Phase 4 (drag to/from) | `tests/e2e/test_annotation_tabs.py` | `test_organise_tab_untagged_highlight_in_untagged_column` | Creates highlight without assigning a tag, switches to Organise tab, verifies card appears in an "Untagged" column |

### three-tab-ui.AC3: CRDT extended with new shared types

| AC | Type | Phase | Test File | Test Name(s) | Verification |
|----|------|-------|-----------|---------------|--------------|
| AC3.1 | Unit | Phase 2, Tasks 1-2 | `tests/unit/test_annotation_doc.py` | `TestTagOrder::test_get_tag_order_empty_tag`, `test_set_and_get_tag_order`, `test_set_tag_order_replaces_existing`, `test_move_highlight_to_tag_appends`, `test_move_highlight_to_tag_at_position`, `test_move_highlight_to_tag_updates_highlight_tag`, `test_move_highlight_to_tag_nonexistent_highlight`, `test_tag_order_syncs_between_docs` | Verifies tag_order Map stores/retrieves ordered IDs per tag, move operations work, and state syncs between CRDT docs (simulating persistence across restart) |
| AC3.2 | Unit | Phase 2, Task 3 | `tests/unit/test_annotation_doc.py` | `TestResponseDraft::test_response_draft_property_returns_xml_fragment`, `test_response_draft_coexists_with_other_fields`, `test_response_draft_survives_full_state_sync`, `TestResponseDraftMarkdown::test_response_draft_markdown_property`, `test_get_response_draft_markdown_empty`, `test_response_draft_markdown_round_trip`, `test_response_draft_markdown_coexists` | Verifies XmlFragment and Text fields are accessible, coexist with existing highlights/client_meta/general_notes, and survive full-state sync |
| AC3.3 | Unit | Phase 2, Task 3 | `tests/unit/test_annotation_doc.py` | `TestCrdtCoexistence::test_existing_highlights_unaffected`, `test_existing_general_notes_unaffected`, `test_broadcast_fires_for_all_field_types`, `test_full_state_includes_all_fields` | Verifies adding new fields does not break existing highlight or general_notes operations; broadcast fires for all field types |

### three-tab-ui.AC4: Tab 3 collaborative editor

| AC | Type | Phase | Test File | Test Name(s) | Verification |
|----|------|-------|-----------|---------------|--------------|
| AC4.1 | E2E | Phase 5, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_respond_tab_shows_milkdown_editor` | Navigates to Respond tab, verifies Milkdown editor container is visible with toolbar elements (bold, italic, heading buttons) |
| AC4.2 | E2E | Phase 5, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_respond_tab_two_clients_real_time_sync` | Two browser contexts on Respond tab; client 1 types "Hello World", verifies client 2 sees it via Playwright `wait_for` |
| AC4.3 | E2E | Phase 5, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_respond_tab_late_joiner_sync` | Client 1 types "Initial content" in Respond tab. Client 2 then opens same workspace and switches to Respond tab. Verifies client 2 editor contains "Initial content" |
| AC4.4 | E2E | Phase 5, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_respond_tab_reference_panel_shows_highlights` | Creates highlights with different tags on Annotate tab, switches to Respond tab, verifies right panel shows highlights grouped under tag headings with correct names and colours |
| AC4.5 | E2E | Phase 5, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_respond_tab_no_highlights_shows_empty_reference` | Navigates to Respond tab on workspace with content but no highlights; verifies reference panel shows empty/placeholder message and Milkdown editor is functional (can type text) |

### three-tab-ui.AC5: Cross-tab navigation and reactivity

| AC | Type | Phase | Test File | Test Name(s) | Verification |
|----|------|-------|-----------|---------------|--------------|
| AC5.1 | E2E | Phase 6, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_locate_button_warps_to_tab1_and_scrolls`, `test_locate_button_from_tab3_warps_to_tab1` | Creates highlight, switches to Organise/Respond tab, clicks "locate" button, verifies active tab changes to "Annotate" and highlight char span is visible in viewport |
| AC5.2 | E2E | Phase 6, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_new_highlight_appears_in_tab2`, `test_new_highlight_appears_in_tab3_reference` | Two contexts: context 1 on Tab 2 (or Tab 3), context 2 creates highlight on Tab 1; verifies context 1 sees new highlight in correct column (or reference panel) without refresh |
| AC5.3 | E2E | Phase 6, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_tab2_tag_change_updates_tab1_sidebar` | Two contexts: context 1 on Tab 1, context 2 on Tab 2 drags highlight to different tag column; verifies context 1 sidebar card shows new tag colour/label |
| AC5.4 | E2E | Phase 6, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_warp_does_not_affect_other_user` | Two contexts both on Tab 2; context 1 clicks "locate"; verifies context 1 switches to Annotate tab while context 2 remains on Organise tab |
| AC5.5 | E2E | Phase 6, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_return_to_previous_tab_after_warp` | Switches to Organise tab, scrolls down, clicks "locate" (warps to Tab 1), clicks Organise tab header to return; verifies Tab 2 content is still rendered (not re-initialised) |

### three-tab-ui.AC6: PDF export includes response draft

| AC | Type | Phase | Test File | Test Name(s) | Verification |
|----|------|-------|-----------|---------------|--------------|
| AC6.1 | E2E | Phase 7, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_pdf_export_includes_response_draft` | Creates content/highlights, switches to Respond tab, types "This is my response draft", clicks Export PDF, verifies the exported PDF (or intermediate .tex file) contains the draft text |
| AC6.2 | E2E | Phase 7, Task 4 | `tests/e2e/test_annotation_tabs.py` | `test_pdf_export_empty_draft_no_extra_section` | Creates content/highlights, does NOT visit Respond tab, clicks Export PDF, verifies PDF does not contain a "General Notes" section |
| AC6.3 | E2E + Unit | Phase 7, Task 4; Phase 2, Task 3 | `tests/e2e/test_annotation_tabs.py`, `tests/unit/test_annotation_doc.py` | `test_pdf_export_without_visiting_tab3`, `TestResponseDraftMarkdown::test_response_draft_markdown_round_trip` | Two contexts: context 1 visits Respond tab and types "Response content"; context 2 (never visits Tab 3) clicks Export PDF; verifies PDF includes "Response content" via CRDT Text field fallback. Unit test validates the round-trip mechanism that the fallback depends on |

---

## Human Verification Required

| AC | Phase | What to Verify | Why Not Automated |
|----|-------|----------------|-------------------|
| AC1.1 | Phase 1 | Visual layout of three tab headers matches design -- correct spacing, alignment, font size, Quasar tab styling | E2E can assert element existence and text, but cannot judge visual polish or CSS layout fidelity |
| AC1.2 | Phase 1 | Cursor/selection awareness rendering (coloured cursors for other users) works within Tab 1 the same as before | Cursor presence rendering is visual and transient; E2E tests can verify highlight CRDT sync but not real-time cursor overlay correctness |
| AC1.4 | Phase 1 | Scroll position is truly preserved after tab switch (not just "page doesn't jump to top") | E2E can check approximate scroll offset but browser scroll behaviour varies; manual verification confirms smooth UX |
| AC2.1 | Phase 3 | Tag column headers have visually correct colour backgrounds and text contrast | E2E can check element existence; visual colour rendering and contrast are best judged by a human |
| AC2.3 | Phase 4 | Drag affordance is visually clear (cursor changes, drag ghost image, drop target highlighting) | HTML5 drag visual feedback (ghost image, cursor style) cannot be verified by Playwright assertions |
| AC2.4 | Phase 4 | Smooth animation or visual transition when card moves between columns | Animation quality is a UX concern beyond assertion capability |
| AC2.5 | Phase 4 | Two users dragging simultaneously feels responsive and non-janky | Concurrency E2E can verify final state correctness but not perceived smoothness during the interaction |
| AC4.1 | Phase 5 | Milkdown toolbar is fully functional -- all buttons (bold, italic, heading, list, code, etc.) produce correct formatting | E2E can verify toolbar presence; verifying every toolbar button produces correct output requires exhaustive interaction testing better done manually |
| AC4.2 | Phase 5 | Character-level merging looks correct visually (no jumbled text, cursor position sane after remote edit) | E2E verifies content convergence; visual cursor behaviour during concurrent editing requires human judgement |
| AC4.4 | Phase 5 | Reference panel layout is visually readable -- tag colour headers, card spacing, scrollability | E2E checks data correctness; visual layout and usability require human review |
| AC5.1 | Phase 6 | Scroll animation is smooth and highlight is centred in viewport after warp | E2E can check visibility; smoothness of `scrollIntoView({behavior:'smooth'})` is a UX judgement |
| AC5.5 | Phase 6 | Scroll position within Tab 2/Tab 3 is preserved after warping to Tab 1 and returning | NiceGUI preserves DOM state but scroll position preservation depends on browser/Quasar behaviour -- manual verification confirms |
| AC6.1 | Phase 7 | PDF rendering of response draft content is visually correct -- formatting (bold, italic, headings, lists) carried through from Milkdown markdown | E2E can check text presence in .tex output; visual quality of the compiled PDF requires human review |

---

## Test Summary by File

### `tests/unit/test_annotation_doc.py`

Existing file, extended with new test classes:

| Test Class | ACs Covered | Phase |
|------------|-------------|-------|
| `TestTagOrder` (8 tests) | AC3.1 | Phase 2 |
| `TestResponseDraft` (3 tests) | AC3.2 | Phase 2 |
| `TestResponseDraftMarkdown` (4 tests) | AC3.2, AC6.3 | Phase 2 |
| `TestCrdtCoexistence` (4 tests) | AC3.3 | Phase 2 |

### `tests/unit/pages/test_annotation_tags.py`

New file:

| Test Name | ACs Covered | Phase |
|-----------|-------------|-------|
| `test_brief_tags_to_tag_info_returns_all_tags` | AC2.1 | Phase 3 |
| `test_tag_info_names_are_title_case` | AC2.1 | Phase 3 |
| `test_tag_info_colours_are_hex` | AC2.1 | Phase 3 |
| `test_tag_info_colours_match_tag_colors` | AC2.1 | Phase 3 |

### `tests/unit/pages/test_annotation_drag.py`

New file:

| Test Name | ACs Covered | Phase |
|-----------|-------------|-------|
| `test_create_drag_state_returns_independent_instances` | AC2.3 | Phase 4 |
| `test_create_drag_state_tracks_dragged_id` | AC2.3 | Phase 4 |
| `test_create_drag_state_clears_on_drop` | AC2.3 | Phase 4 |

### `tests/e2e/test_annotation_tabs.py`

New file, all E2E tests (Playwright):

| Test Name | ACs Covered | Phase |
|-----------|-------------|-------|
| `test_tab_headers` | AC1.1 | Phase 1 |
| `test_deferred_rendering` | AC1.3 | Phase 1 |
| (state preservation test) | AC1.2, AC1.4 | Phase 1 |
| (multi-client sync test) | AC1.2 | Phase 1 |
| `test_organise_tab_shows_tag_columns` | AC2.1 | Phase 3 |
| `test_organise_tab_highlight_in_correct_column` | AC2.2 | Phase 3 |
| `test_organise_tab_card_shows_author_and_text` | AC2.2 | Phase 3 |
| `test_organise_tab_untagged_highlight_in_untagged_column` | AC2.6 | Phase 3 |
| `test_drag_reorder_within_column` | AC2.3 | Phase 4 |
| `test_drag_between_columns_changes_tag` | AC2.4 | Phase 4 |
| `test_drag_between_columns_updates_tab1_sidebar` | AC2.4 | Phase 4 |
| `test_concurrent_drag_produces_consistent_result` | AC2.5 | Phase 4 |
| `test_respond_tab_shows_milkdown_editor` | AC4.1 | Phase 5 |
| `test_respond_tab_two_clients_real_time_sync` | AC4.2 | Phase 5 |
| `test_respond_tab_late_joiner_sync` | AC4.3 | Phase 5 |
| `test_respond_tab_reference_panel_shows_highlights` | AC4.4 | Phase 5 |
| `test_respond_tab_no_highlights_shows_empty_reference` | AC4.5 | Phase 5 |
| `test_locate_button_warps_to_tab1_and_scrolls` | AC5.1 | Phase 6 |
| `test_locate_button_from_tab3_warps_to_tab1` | AC5.1 | Phase 6 |
| `test_new_highlight_appears_in_tab2` | AC5.2 | Phase 6 |
| `test_new_highlight_appears_in_tab3_reference` | AC5.2 | Phase 6 |
| `test_tab2_tag_change_updates_tab1_sidebar` | AC5.3 | Phase 6 |
| `test_warp_does_not_affect_other_user` | AC5.4 | Phase 6 |
| `test_return_to_previous_tab_after_warp` | AC5.5 | Phase 6 |
| `test_pdf_export_includes_response_draft` | AC6.1 | Phase 7 |
| `test_pdf_export_empty_draft_no_extra_section` | AC6.2 | Phase 7 |
| `test_pdf_export_without_visiting_tab3` | AC6.3 | Phase 7 |

---

## Test Execution Commands

### Unit tests only (fast, no DB or browser required)

```bash
# All CRDT extension tests (Phase 2)
uv run pytest tests/unit/test_annotation_doc.py -v

# Tag_order tests specifically
uv run pytest tests/unit/test_annotation_doc.py::TestTagOrder -v

# Response draft tests specifically
uv run pytest tests/unit/test_annotation_doc.py::TestResponseDraft -v
uv run pytest tests/unit/test_annotation_doc.py::TestResponseDraftMarkdown -v

# CRDT coexistence tests
uv run pytest tests/unit/test_annotation_doc.py::TestCrdtCoexistence -v

# TagInfo abstraction tests (Phase 3)
uv run pytest tests/unit/pages/test_annotation_tags.py -v

# Drag state tests (Phase 4)
uv run pytest tests/unit/pages/test_annotation_drag.py -v
```

### E2E tests (require live app server + Playwright)

```bash
# All tab E2E tests
uv run pytest tests/e2e/test_annotation_tabs.py -v

# Phase 1: Tab container shell
uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_tab_headers or test_deferred_rendering"

# Phase 3: Tag columns (read-only)
uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_organise"

# Phase 4: Drag-and-drop
uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_drag"

# Phase 5: Milkdown editor
uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_respond"

# Phase 6: Warp navigation and cross-tab reactivity
uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_locate or test_warp or test_new_highlight or test_tab2_tag"

# Phase 7: PDF export with response draft
uv run pytest tests/e2e/test_annotation_tabs.py -v -k "test_pdf_export"
```

### Full regression (unit + integration, excludes E2E)

```bash
uv run test-all
```

### Smart test selection (based on changed files)

```bash
uv run test-debug
```

---

## AC Coverage Matrix

A cross-reference showing that every AC has at least one automated test and identifying which also need human verification.

| AC | Automated | Human | Notes |
|----|-----------|-------|-------|
| AC1.1 | Yes (E2E) | Yes | Visual layout polish |
| AC1.2 | Yes (E2E) | Yes | Cursor presence rendering |
| AC1.3 | Yes (E2E) | No | |
| AC1.4 | Yes (E2E) | Yes | Scroll position precision |
| AC2.1 | Yes (Unit + E2E) | Yes | Colour contrast |
| AC2.2 | Yes (E2E) | No | |
| AC2.3 | Yes (E2E) | Yes | Drag affordance UX |
| AC2.4 | Yes (E2E) | Yes | Animation smoothness |
| AC2.5 | Yes (E2E) | Yes | Perceived responsiveness |
| AC2.6 | Yes (E2E) | No | |
| AC3.1 | Yes (Unit) | No | |
| AC3.2 | Yes (Unit) | No | |
| AC3.3 | Yes (Unit) | No | |
| AC4.1 | Yes (E2E) | Yes | Toolbar completeness |
| AC4.2 | Yes (E2E) | Yes | Visual cursor behaviour |
| AC4.3 | Yes (E2E) | No | |
| AC4.4 | Yes (E2E) | Yes | Panel layout readability |
| AC4.5 | Yes (E2E) | No | |
| AC5.1 | Yes (E2E) | Yes | Scroll smoothness |
| AC5.2 | Yes (E2E) | No | |
| AC5.3 | Yes (E2E) | No | |
| AC5.4 | Yes (E2E) | No | |
| AC5.5 | Yes (E2E) | Yes | Scroll position preservation |
| AC6.1 | Yes (E2E) | Yes | PDF formatting quality |
| AC6.2 | Yes (E2E) | No | |
| AC6.3 | Yes (E2E + Unit) | No | |

**Totals:** 26/26 ACs have automated tests. 13/26 ACs additionally require human verification (all for visual/UX quality reasons that are beyond assertion capability).
