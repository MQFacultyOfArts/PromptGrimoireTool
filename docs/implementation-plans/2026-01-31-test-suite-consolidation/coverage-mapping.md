# Test Suite Consolidation - Coverage Mapping

**Created:** 2026-02-01
**Issue:** #93 (Seam A: Workspace Model)
**Epic:** #92 (Annotation Workspace Platform)

## Summary

| Demo File | Total Tests | Covered | Blocked | Not Needed |
|-----------|-------------|---------|---------|------------|
| test_live_annotation.py | 23 | 15 | 6 | 2 |
| test_text_selection.py | 12 | 0 | 0 | 12 |
| test_two_tab_sync.py | 21 | 9 | 0 | 12 |
| test_user_isolation.py | 7 | 2 | 0 | 5 |
| **Total** | **63** | **26** | **6** | **31** |

## Coverage by New Test File

| New File | Tests | Coverage From |
|----------|-------|---------------|
| test_annotation_basics.py | 9 | Page loading, workspace creation |
| test_annotation_cards.py | 11 | Card UI, comments, tags, go-to-text |
| test_annotation_highlights.py | 21 | Highlight CRUD, mutations, edge cases, keyboard |
| test_annotation_workflows.py | 5 | Complete workflows, Definition of Done |
| test_annotation_sync.py | 8 | Two-context sync (replaces test_two_tab_sync.py) |
| test_annotation_collab.py | 4+2 | Multi-user collaboration (2 skipped for Issue #11) |
| test_auth_pages.py | 14 | Auth flows (pre-existing, covers isolation) |

## Blocked Tests (Seam G - Issue #99)

Paragraph detection tests cannot be migrated until Seam G is implemented:

### TestAnnotationCardParagraphNumbers (5 tests)
- `test_highlight_in_paragraph_shows_para_number`
- `test_highlight_in_metadata_shows_no_para_number`
- `test_highlight_in_paragraph_48_shows_para_number`
- `test_highlight_in_court_orders_shows_para_48`
- `test_page_loads` (demo-specific page load)

### TestMultiParagraphHighlights (1 test)
- `test_highlight_spanning_paragraphs_shows_range`

These tests currently live in `tests/e2e/test_live_annotation.py` and will be migrated when paragraph detection is implemented.

## Detailed Coverage Mapping

### test_live_annotation.py

| Test Class | Tests | Status | Location |
|------------|-------|--------|----------|
| TestAnnotationCardParagraphNumbers | 5 | BLOCKED | Seam G (#99) |
| TestHighlightCreation | 2 | COVERED | test_annotation_highlights.py::TestHighlightCreation |
| TestMultiParagraphHighlights | 1 | BLOCKED | Seam G (#99) |
| TestHighlightDeletion | 1 | COVERED | test_annotation_highlights.py::TestHighlightMutations |
| TestCommentCreation | 1 | COVERED | test_annotation_cards.py::TestAnnotationCards |
| TestKeyboardShortcuts | 2 | COVERED | test_annotation_highlights.py::TestHighlightMutations |
| TestGoToTextButton | 1 | COVERED | test_annotation_cards.py::TestAnnotationCards |
| TestTagColors | 2 | COVERED | test_annotation_cards.py::TestTagSelection |
| TestMultipleHighlights | 2 | COVERED | test_annotation_workflows.py::TestFullAnnotationWorkflow |
| TestOverlappingHighlights | 4 | PARTIAL | 1 in test_annotation_highlights.py (selection edge cases demo-specific) |
| TestMultiUserCollaboration | 2 | COVERED | test_annotation_collab.py |

### test_text_selection.py

| Test Class | Tests | Status | Notes |
|------------|-------|--------|-------|
| TestPageLoads | 2 | NOT NEEDED | Demo page specific |
| TestTextSelection | 3 | IMPLICIT | Click+shift covered by helper usage |
| TestEmptySelection | 1 | NOT NEEDED | Click-only edge case for demo |
| TestVisualHighlight | 4 | COVERED | test_annotation_highlights.py::TestHighlightCreation |
| TestClickDragSelection | 1 | NOT NEEDED | Annotation uses click+shift, not drag |
| TestEdgeCases | 1 | IMPLICIT | Multiline selection implicit in helper |

**Decision:** All text_selection tests are either demo-page specific, implicitly covered by helper function usage in annotation tests, or use drag selection which annotation doesn't use. No migration needed.

### test_two_tab_sync.py

| Test Class | Tests | Status | Notes |
|------------|-------|--------|-------|
| TestTwoTabBasicSync | 4 | REPLACED | test_annotation_sync.py::TestHighlightSync |
| TestMultipleUpdates | 2 | REPLACED | test_annotation_sync.py concurrent operations |
| TestConcurrentEdits | 1 | REPLACED | test_annotation_sync.py::TestConcurrentOperations |
| TestEdgeCases | 4 | PARTIAL | Unicode/long content not tested in annotation |
| TestLateJoiner | 2 | REPLACED | test_annotation_sync.py::TestSyncEdgeCases |
| TestThreeOrMoreTabs | 1 | DEFER | Could add if needed |
| TestDisconnectReconnect | 2 | PARTIAL | Refresh tested, close partially tested |
| TestCharacterByCharacterSync | 2 | NOT NEEDED | Text editing, not highlights |
| TestCursorPositionSync | 3 | NOT NEEDED | Text editing, not highlights |

**Decision:** Text-editing CRDT tests (character-by-character, cursor position) are not applicable to annotation highlight CRDT. Core sync functionality is covered.

### test_user_isolation.py

| Test Class | Tests | Status | Notes |
|------------|-------|--------|-------|
| TestLiveAnnotationUserIsolation | 3 | MIXED | 1 demo-specific, 2 covered by auth_pages |
| TestCRDTSyncUserIsolation | 2 | NOT NEEDED | Demo-specific document ID tests |
| TestTextSelectionUserIsolation | 2 | COVERED | test_auth_pages.py::TestProtectedPage |

**Decision:** Auth redirect tests already covered by comprehensive `test_auth_pages.py`. Demo-specific document isolation tests not applicable to /annotation route.

## Tests Not Needed (Rationale)

### Demo-Specific Tests
- Page load tests for demo routes
- Demo-specific document ID format tests
- Demo-specific user document isolation

### Selection Mechanism Differences
- Demo uses drag selection
- Annotation uses click+shift selection
- Drag selection edge cases don't apply

### Text Editing vs Highlight CRDT
- Demo tests raw text CRDT editing
- Annotation tests highlight CRDT operations
- Character/cursor sync not applicable

## Gap Analysis

### Known Gaps (Low Priority)
1. **Unicode content sync** - Could add test for emoji/CJK content in highlights
2. **Three or more contexts** - Only testing two contexts currently
3. **Very long content** - Could stress test with large documents

### Mitigations
- Core sync functionality thoroughly tested
- Edge cases less likely in production use
- Can add tests if bugs emerge

## Files to Deprecate in Phase 6

1. `tests/e2e/test_live_annotation.py` - Replaced by segmented annotation tests
2. `tests/e2e/test_text_selection.py` - Demo-specific, not applicable
3. `tests/e2e/test_two_tab_sync.py` - Replaced by test_annotation_sync.py
4. `tests/e2e/test_user_isolation.py` - Covered by test_auth_pages.py
