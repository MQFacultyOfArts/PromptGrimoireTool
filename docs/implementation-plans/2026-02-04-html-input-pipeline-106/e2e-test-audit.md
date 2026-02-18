# E2E Test Audit: Pseudocode User Actions and Duplicate Analysis

**Date:** 2026-02-06 (revised 2026-02-09)
**Context:** Issue #106 changed content input from plain-text `.fill()` to HTML clipboard paste. 8 of 15 E2E test files are SKIPPED pending this redesign.

## Migration Status: COMPLETE (2026-02-17)

**Issue:** #156
**Design:** docs/design-plans/2026-02-14-156-e2e-test-migration.md

### Files Deleted (12)
- test_annotation_basics.py
- test_annotation_cards.py
- test_annotation_workflows.py
- test_subtests_validation.py
- test_annotation_highlights.py
- test_annotation_sync.py
- test_annotation_collab.py
- test_annotation_blns.py
- test_annotation_cjk.py
- test_i18n_pdf_export.py
- test_dom_performance.py (benchmark)
- test_pdf_export.py (skipped stub)

### Files Created (5 persona tests)
- test_instructor_workflow.py — instructor course setup workflow
- test_law_student.py — AustLII paste, annotation, PDF export
- test_translation_student.py — CJK/RTL/mixed-script annotation, i18n PDF export
- test_history_tutorial.py — bidirectional real-time collaboration
- test_naughty_student.py — dead-end navigation, BLNS/XSS injection, copy protection bypass

### Files Fixed (4)
- conftest.py — _textNodes readiness in fixtures
- test_annotation_tabs.py — text walker helpers
- test_html_paste_whitespace.py — text walker helpers
- test_fixture_screenshots.py — _textNodes readiness wait

### Issues Closable
- #156: All data-char-index references removed, E2E suite migrated
- #106: HTML paste works end-to-end (test_law_student.py clipboard paste)
- #101: CJK/RTL content works (test_translation_student.py); BLNS edge cases handled (test_naughty_student.py)

---

## Part 1: Every E2E Test as User Actions

### File: test_auth_pages.py (ACTIVE)

**TestLoginPage.test_login_page_elements_and_magic_link**
```
User goes to /login
  → sees email input, send-magic-link button, SSO button
User types "test@example.com", clicks send magic link
  → sees "Magic link sent" confirmation
User reloads /login, types "arbitrary@anywhere.com", clicks send
  → sees "Magic link sent" confirmation
```

**TestMagicLinkCallback.test_callback_token_handling**
```
User visits /auth/callback?token=<valid>
  → redirected to /
User logs out, visits /auth/callback?token=bad-token
  → sees "Error: invalid_token", redirected to /login
User visits /auth/callback (no token)
  → sees "Invalid or missing token", redirected to /login
```

**TestSSOFlow.test_sso_authentication_flow**
```
User goes to /login, clicks SSO button
  → browser navigates to mock.stytch.com with connection_id + public_token params
User visits /auth/sso/callback?token=<valid-sso>
  → redirected to /
User logs out, visits /auth/sso/callback?token=bad-sso-token
  → sees "invalid_token", redirected to /login
```

**TestProtectedPage.test_protected_page_unauthenticated**
```
Unauthenticated user visits /protected
  → redirected to /login
```

**TestProtectedPage.test_protected_page_authenticated_flow**
```
User authenticates via magic link
User visits /protected
  → sees "test@example.com" and "stytch_member"
User clicks logout
  → redirected to /login
User revisits /protected
  → redirected to /login (session cleared)
```

**TestSessionPersistence.test_session_persists**
```
User authenticates via magic link, goes to /protected
User refreshes page
  → still on /protected, sees email
User navigates to /login, then back to /protected
  → still on /protected (session persists across navigation)
```

---

### File: test_annotation_basics.py (SKIPPED → needs reimplementation)

**TestAnnotationPageBasic.test_annotation_page_states**
```
User goes to /annotation
  → page loads, sees "create workspace" button
User goes to /annotation?workspace_id=<invalid-uuid>
  → sees "not found"
```

**TestWorkspaceAndDocumentCreation.test_workspace_and_document_crud**
```
Authenticated user goes to /annotation, clicks "Create"
  → URL contains workspace_id=<valid-UUID>, page shows UUID
User pastes content, clicks Add Document
  → char spans appear (>= 8 spans for test content)
User reloads workspace URL
  → document content still visible
```

---

### File: test_annotation_highlights.py (SKIPPED → needs reimplementation)

**TestHighlightCreation.test_select_text_shows_highlight_menu**
```
User creates workspace, adds document
User selects chars 0-2 by mouse drag
  → tag toolbar becomes visible
```

**TestHighlightCreation.test_create_highlight_applies_styling**
```
User creates workspace, adds document
User selects chars 0-1, clicks first tag
  → char[0] has rgba background-color
```

**TestHighlightCreation.test_highlight_persists_after_reload**
```
User creates workspace, adds document
User creates highlight on chars 0-1
  → "Saved" indicator appears
User reloads workspace URL
  → char[0] still has rgba background-color
```

**TestHighlightMutations.test_highlight_mutations**
```
User creates workspace, adds document, creates highlight on chars 0-1
  (card visible)
Subtest "change_tag": User clicks tag dropdown, selects "Legal Issues"
  → char background changes to red (rgba(214,39,40))
Subtest "delete": User clicks delete button on card
  → card disappears, char styling removed
```

**TestHighlightInteractions.test_highlight_interactions**
```
User creates workspace with 100 words, scrolls to word 90, highlights 90-92
  (card visible)
Subtest "goto": User scrolls to top, clicks goto button on card
  → word 90 is visible in viewport
Subtest "hover": User hovers over card
  → word 90 has "card-hover-highlight" class
```

**TestEdgeCasesConsolidated.test_edge_cases**
```
Subtest "keyboard shortcut": User creates workspace, selects chars, presses "1"
  → char has Jurisdiction blue background, card visible
Subtest "overlapping": User creates workspace, highlights chars 1-3 (Jurisdiction),
  then highlights chars 2-4 (Legal Issues)
  → chars 2-3 have rgba background, 2 annotation cards
Subtest "special chars": User creates workspace with "<script> & "quotes""
  → char spans appear, can create highlight
Subtest "empty content": User creates workspace, clicks Add without content
  → error notification visible
```

---

### File: test_annotation_cards.py (SKIPPED → needs reimplementation)

**TestAnnotationCards.test_annotation_card_behaviour**
```
User creates workspace, adds "The defendant was negligent", highlights "The"
Subtest "card appears": → annotation card visible
Subtest "text preview": → card contains "The"
Subtest "add comment": User types "This is my comment", clicks Post
  → card shows "This is my comment"
```

**TestAnnotationCards.test_comment_persistence**
```
User creates workspace, adds document, highlights "Persistent", adds comment
  → "Saved" indicator
User reloads workspace URL
  → card still shows "Persistent comment"
```

**TestTagSelection.test_tag_toolbar_and_highlight_creation**
```
User creates workspace, adds document
Subtest "toolbar visible": → tag toolbar visible
Subtest "tag creates highlight": User selects chars 4-8, clicks first tag
  → char[4] has rgba background
```

---

### File: test_annotation_workflows.py (SKIPPED → CONSOLIDATE then DELETE)

**TestFullAnnotationWorkflow.test_complete_annotation_workflow**
```
User goes to /annotation, creates workspace
User adds document, creates highlight on chars 0-2
  → card visible, "Saved" indicator
User reloads workspace URL
  → char[0] still highlighted
```
**DUPLICATE of**: test_highlight_persists_after_reload + test_workspace_and_document_crud

**TestFullAnnotationWorkflow.test_multiple_highlights_persist**
```
User creates workspace, adds document
User highlights chars 0-1, waits for save
User highlights chars 4-5, waits for save
  → 2 annotation cards
User reloads
  → both chars still highlighted
```
**PARTIAL DUPLICATE of**: test_highlight_persists_after_reload (just tests 2 instead of 1)

**TestPdfExport.test_export_pdf_button_visible**
```
User creates workspace, adds document, creates highlight
  → Export PDF button visible
```
**SUPERSEDED by**: test_pdf_export.py which actually downloads and verifies PDF

**TestDefinitionOfDone.test_full_annotation_workflow_with_tags_and_export**
```
User creates workspace, adds legal content
User highlights chars 1-3 as "Legal Issues", chars 53 as "Decision"
User adds comment "Key finding - establishes duty of care"
  → "Saved", highlights visible, export button visible
```
**PARTIAL DUPLICATE of**: test_pdf_export.py full workflow test (which actually exports PDF)

---

### File: test_annotation_sync.py (SKIPPED → needs reimplementation)

**TestHighlightSync.test_highlight_sync_bidirectional**
```
Two users viewing same workspace with content
User1 highlights chars 0-1
  → User2 sees char[0] highlighted
User2 highlights chars 2-3
  → User1 sees char[2] highlighted
```

**TestHighlightSync.test_highlight_deletion_syncs**
```
User1 creates highlight, User2 sees it
User1 deletes highlight via card
  → User2's char styling removed
```

**TestCommentSync.test_comment_added_in_context1_appears_in_context2**
```
User1 creates highlight, adds comment "Test comment from context 1"
  → User2 sees card with "Test comment from context 1"
```

**TestTagChangeSync.test_tag_changed_in_context1_updates_in_context2**
```
User1 creates highlight (default tag)
User1 changes tag to "Legal Issues"
  → User2 sees char color change to red
```

**TestConcurrentOperations.test_concurrent_highlights_both_appear**
```
User1 selects chars 0-1, User2 selects chars 3-4 (simultaneously)
Both click tag buttons
  → Both users see both highlights, 2 cards each
```

**TestSyncEdgeCases.test_sync_edge_cases**
```
User1 creates highlight, User2 sees it
Subtest "refresh preserves": User2 reloads → still highlighted
Subtest "late joiner": User3 joins workspace → sees existing highlight + card
```

---

### File: test_annotation_collab.py (SKIPPED → needs reimplementation)

**TestMultiUserHighlights.test_two_users_see_each_others_highlights**
```
User1 (alice) highlights chars 0-1 → syncs to User2 (bob)
User2 highlights chars 3-4 → syncs to User1
Both see 2 cards
```
**DUPLICATE of**: test_highlight_sync_bidirectional (identical logic, just uses authenticated contexts)

**TestMultiUserHighlights.test_highlight_deletion_by_creator_syncs**
```
User1 creates highlight, User2 sees it
User1 deletes → User2 sees styling removed
```
**DUPLICATE of**: test_highlight_deletion_syncs (identical logic)

**TestUserCountBadge.test_user_count_shows_two_when_both_connected**
```
Two authenticated users viewing same workspace
  → both see user count badge = "2"
```

**TestUserCountBadge.test_user_count_updates_when_user_leaves**
```
Two users connected (badge shows 2)
User2 disconnects
  → User1's badge shows "1"
```

**TestConcurrentCollaboration.test_concurrent_edits_both_preserved**
```
User1 selects char 0, User2 selects char 4 (simultaneously)
Both click tag buttons
  → both see both highlights
```
**DUPLICATE of**: test_concurrent_highlights_both_appear (identical logic)

**TestConcurrentCollaboration.test_comment_thread_from_both_users**
```
User1 creates highlight, both see card
User1 adds "Comment from user 1" → syncs to User2
User2 adds "Reply from user 2" → syncs to User1
```
**UNIQUE**: tests bidirectional comment threading

---

### File: test_annotation_blns.py (SKIPPED → needs reimplementation)

**TestBLNSEdgeCases.test_individual_cjk_characters** (parametrized x10)
```
User creates workspace with single CJK char
  → char span visible, text matches
```

**TestBLNSEdgeCases.test_rtl_arabic_text**
```
User creates workspace with "مرحبا"
  → 5 char spans visible
```

**TestBLNSEdgeCases.test_rtl_hebrew_text**
```
User creates workspace with "שלום"
  → can select chars 0-3
```

**TestBLNSEdgeCases.test_hard_whitespace_nbsp**
```
User creates workspace with "Hello\u00a0World"
  → char[5] (nbsp) visible
```

**TestBLNSEdgeCases.test_ideographic_space**
```
User creates workspace with "你\u3000好"
  → 3 char spans visible
```

---

### File: test_annotation_cjk.py (SKIPPED → needs reimplementation)

**TestCJKCharacterSelection.test_chinese_character_selection**
```
User creates workspace with "你好世界"
  → can select chars 1-2, both visible
```

**TestCJKCharacterSelection.test_japanese_mixed_script**
```
User creates workspace with "こんにちは世界"
  → 7 char spans all visible
```

**TestCJKCharacterSelection.test_korean_character_selection**
```
User creates workspace with "안녕하세요"
  → can highlight chars 0-2, char[0] has rgba background
```

**TestCJKCharacterSelection.test_cjk_mixed_with_ascii**
```
User creates workspace with "Hello 世界 World"
  → can select chars 6-7, both visible
```

---

### File: test_html_paste_whitespace.py (ACTIVE)

**TestHTMLPasteWhitespace.test_libreoffice_paste_no_excessive_whitespace**
```
User creates workspace, pastes LibreOffice HTML (183-clipboard fixture)
  → editor shows "Content pasted" placeholder
User clicks Add Document
  → "Case Name", "Lawlis", "Medium Neutral Citation" all in rendered text
  → vertical gap between "Case Name" and "Citation" < 100px
```

**TestHTMLPasteWhitespace.test_paste_preserves_table_structure**
```
User pastes LibreOffice HTML, clicks Add
  → "Case Name" and "Lawlis v R" on same row (Y diff < 30px)
```

**TestParagraphNumberingAndIndent.test_ground_1_indent_preserved**
```
User pastes LibreOffice HTML, clicks Add
  → "Ground 1" text has indent 60-120px (2.38cm margin-left)
```

**TestParagraphNumberingAndIndent.test_paragraph_numbering_starts_at_4**
```
User pastes LibreOffice HTML, clicks Add
  → DOM has <ol start="4"> containing first list item
```

**TestParagraphNumberingAndIndent.test_highest_paragraph_number_is_48**
```
User pastes LibreOffice HTML, clicks Add
  → highest paragraph number from ol start + li count = 48
```

**TestPasteHandlerConsoleOutput.test_paste_triggers_cleanup**
```
User pastes LibreOffice HTML
  → console has "[PASTE]" log with "bytes" + reduction percentage
```

---

### File: test_fixture_screenshots.py (ACTIVE)

**TestFixtureScreenshots.test_capture_fixture_screenshots** (parametrized x16)
```
User creates workspace, pastes fixture HTML, clicks Add
  → captures screenshots at top + landmark positions
  → always passes (visual QA only)
```

---

### File: test_pdf_export.py (SKIPPED — stubbed, needs rewrite)

**TestPdfExportWorkflow.test_two_users_collaborate_and_export_pdf**
```
STUBBED (pass). Workflow documented in module docstring:
Alice creates workspace, pastes AustLII HTML
Alice creates 10 annotations covering all tags with overlapping highlights:
  - jurisdiction, legally_relevant_facts, legal_issues, reasons (x2),
    courts_reasoning, decision, order, domestic_sources, reflection
  - Overlap edge cases: order+reasons, domestic_sources+reflection, reasons→courts_reasoning adjacent
Alice adds comment on jurisdiction
Bob joins, adds procedural_history on case name
Bob replies to Alice's jurisdiction comment, Alice replies back
Alice adds lipsum comments to courts_reasoning
Alice writes general notes
Alice exports PDF
  → PDF generated successfully
```
**Blocked on**: #106 (HTML paste), #101 (BLNS/Unicode), #76 (proper document upload)

---

### File: test_i18n_pdf_export.py (SKIPPED → needs reimplementation)

**TestI18nPdfExportE2E.test_paste_and_export_i18n_fixture** (parametrized x4)
```
User creates workspace, pastes i18n fixture text, clicks Add
User clicks Export PDF → downloads file
  → PDF exists and valid
```

**TestI18nPdfExportE2E.test_paste_and_export_cjk_mixed**
```
User creates workspace, pastes mixed CJK text, clicks Add
User clicks Export PDF → downloads file
  → PDF valid
```

---

### File: test_subtests_validation.py (ACTIVE → DELETE)

**TestSubtestsValidation.test_subtests_share_fixture**
```
User goes to /
  → body visible, same page object across subtests, title exists
```
**META-TEST**: Validates pytest infrastructure, not user behaviour.

---

### File: tests/benchmark/test_dom_performance.py (ACTIVE, marked `@pytest.mark.e2e`)

**TestFixtureBenchmarks.test_blns_corpus**
```
User creates workspace, pastes BLNS unicode corpus, clicks Add
  → measures render time, DOM node count, selection latency, scroll performance
```

**TestFixtureBenchmarks.test_austlii_183**
```
User creates workspace, pastes AustLII legal document text, clicks Add
  → measures render time, DOM node count, selection latency, scroll performance
```

**TestFixtureBenchmarks.test_conversation** (parametrized across all conversation fixtures)
```
User creates workspace, pastes conversation fixture text, clicks Add
  → measures render time, DOM node count, selection latency, scroll performance
```

**TestFixtureBenchmarks.test_print_summary**
```
Aggregates and prints benchmark results from above tests
  → reports ACCEPTABLE/REVIEW NEEDED based on render time and selection latency thresholds
```

**Note:** Uses `page.evaluate()` for DOM metrics (justified exception to the no-JS-injection rule since benchmarks need performance.memory and node counts that have no Playwright-native equivalent).

---

## Part 2: Duplicate/Overlap Analysis

### Exact or Near-Exact Duplicates (REMOVE one copy)

| Duplicate | In File | Duplicates | In File | Resolution |
|-----------|---------|------------|---------|------------|
| test_two_users_see_each_others_highlights | collab | test_highlight_sync_bidirectional | sync | **Merge into sync** |
| test_highlight_deletion_by_creator_syncs | collab | test_highlight_deletion_syncs | sync | **Merge into sync** |
| test_concurrent_edits_both_preserved | collab | test_concurrent_highlights_both_appear | sync | **Merge into sync** |
| test_complete_annotation_workflow | workflows | test_highlight_persists_after_reload | highlights | **Drop from workflows** |
| test_export_pdf_button_visible | workflows | test_two_users_collaborate_and_export_pdf | pdf_export | **Drop from workflows** |

### Significant Overlap (CONSOLIDATE)

| Test | Overlaps With | Resolution |
|------|--------------|------------|
| test_full_annotation_workflow_with_tags_and_export (workflows) | test_two_users_collaborate_and_export_pdf (pdf_export) | **Drop from workflows** |
| test_multiple_highlights_persist (workflows) | test_highlight_persists_after_reload (highlights) | **Keep both** |
| test_individual_cjk_characters x10 (blns) | test_chinese/japanese/korean (cjk) | **Keep separate** |

### Duplicated Infrastructure (CONSOLIDATE into helpers)

| Pattern | Duplicated In | Proposed Helper |
|---------|--------------|-----------------|
| HTML paste into editor | paste_whitespace, fixture_screenshots, pdf_export | `annotation_helpers.simulate_html_paste()` |
| Auth + workspace + paste + wait | paste_whitespace, fixture_screenshots, pdf_export | `annotation_helpers.setup_workspace_with_html()` |
| Select chars + apply named tag | pdf_export (`_select_chars_and_tag`) | `annotation_helpers.select_chars_and_tag()` |
| paste_ready_page / fixture_page | paste_whitespace, fixture_screenshots | `conftest.clipboard_page` fixture |

---

## Part 3: Deprecated Test Coverage Cross-Reference

The `tests/e2e/deprecated/` directory contains 3 files with ~55 tests. These are garbage (use obsolete routes/fixtures) but their **user actions** must be covered by the active suite. This table maps deprecated actions to their active-suite equivalents.

### deprecated/test_live_annotation.py (20 tests)

| Deprecated Test | User Action | Covered By (active) |
|----------------|-------------|---------------------|
| test_page_loads | Page loads with sample text | test_annotation_basics: test_annotation_page_states |
| test_highlight_in_paragraph_shows_para_number | Highlight shows `[N]` paragraph number | **NOT COVERED** — blocked on Issue #99 (Seam G) |
| test_highlight_in_metadata_shows_no_para_number | Highlight in metadata shows no para number | **NOT COVERED** — blocked on #99 |
| test_highlight_in_paragraph_48_shows_para_number | Para 48 number display | **NOT COVERED** — blocked on #99 |
| test_highlight_in_court_orders_shows_para_48 | Court orders inherit para 48 | **NOT COVERED** — blocked on #99 |
| test_can_select_text_and_create_highlight | Select text, create highlight | test_annotation_highlights: test_create_highlight_applies_styling |
| test_highlight_shows_quoted_text | Card shows highlighted text | test_annotation_cards: test_annotation_card_behaviour ("text preview") |
| test_highlight_spanning_paragraphs_shows_range | Multi-paragraph highlight shows range | **NOT COVERED** — blocked on #99 |
| test_close_button_removes_highlight | Delete highlight via card | test_annotation_highlights: test_highlight_mutations ("delete") |
| test_can_add_comment_to_highlight | Add comment to highlight | test_annotation_cards: test_annotation_card_behaviour ("add comment") |
| test_number_key_applies_tag | Keyboard shortcut creates highlight | test_annotation_highlights: test_edge_cases ("keyboard shortcut") |
| test_key_0_applies_reflection_tag | Key "0" applies reflection tag | **PARTIAL** — test_edge_cases tests key "1" only |
| test_go_to_text_scrolls_to_highlight | Goto button scrolls to highlight | test_annotation_highlights: test_highlight_interactions ("goto") |
| test_jurisdiction_tag_has_blue_border | Tag-specific border color | **NOT COVERED** — tag color verification |
| test_different_tags_have_different_colors | Multiple tags have distinct colors | **NOT COVERED** — tag color verification |
| test_can_create_multiple_highlights | Multiple highlights coexist | test_annotation_highlights: test_edge_cases ("overlapping") |
| test_deleting_one_highlight_keeps_others | Delete one, others persist | **NOT COVERED** — selective deletion |
| test_can_select_starting_on_highlighted_word | Select starting on highlighted text | test_annotation_highlights: test_edge_cases ("overlapping") |
| test_can_create_fully_overlapping_highlights | Fully overlapping highlights | test_annotation_highlights: test_edge_cases ("overlapping") |
| test_can_select_ending_on_highlighted_word | Select ending on highlighted text | **PARTIAL** — overlapping subtest covers adjacent case |
| test_can_select_starting_at_highlight_boundary | Select at exact boundary | **PARTIAL** — overlapping subtest |
| test_two_users_see_each_others_highlights | Multi-user sync | test_annotation_sync: test_highlight_sync_bidirectional |
| test_user_count_updates_with_connections | User count badge | test_annotation_collab: test_user_count_* |

### deprecated/test_text_selection.py (12 tests)

| Deprecated Test | User Action | Covered By (active) |
|----------------|-------------|---------------------|
| test_page_loads_with_sample_text | Page loads | test_annotation_basics |
| test_selection_info_panel_exists | Selection UI panel exists | **IMPLICIT** — tag toolbar visibility in test_annotation_cards |
| test_text_can_be_selected | Text selectable | test_annotation_highlights: test_select_text_shows_highlight_menu |
| test_selection_captured_in_python | Selection captured server-side | **IMPLICIT** — highlight creation proves capture works |
| test_selection_offsets_captured | Selection offsets correct | **IMPLICIT** — char-indexed highlighting proves offsets |
| test_click_without_drag_no_selection | Click without drag = no selection | **NOT COVERED** |
| test_create_highlight_button_exists | Highlight button exists | test_annotation_cards: test_tag_toolbar_and_highlight_creation |
| test_highlight_applied_to_selection | Highlight applies styling | test_annotation_highlights: test_create_highlight_applies_styling |
| test_highlight_has_background_color | Highlight has rgba background | test_annotation_highlights: test_create_highlight_applies_styling |
| test_multiple_highlights_supported | Multiple highlights | test_annotation_highlights: test_edge_cases ("overlapping") |
| test_click_drag_selection | Click-drag selection | test_annotation_highlights: test_select_text_shows_highlight_menu |
| test_multiline_selection | Multiline selection | **NOT COVERED** — no active test selects across lines |

### deprecated/test_user_isolation.py (7 tests)

| Deprecated Test | User Action | Covered By (active) |
|----------------|-------------|---------------------|
| test_different_users_see_different_documents | Users see own documents | **IMPLICIT** — workspace UUID isolation |
| test_unauthenticated_user_redirected_to_login (x3) | Unauth redirects | test_auth_pages: test_protected_page_unauthenticated |
| test_user_identity_shown_correctly | User email displayed | test_auth_pages: test_protected_page_authenticated_flow |
| test_document_id_contains_user_email | Doc ID has user email | **OBSOLETE** — workspace model replaced user-scoped docs |
| test_authenticated_user_can_access | Auth user can access | test_auth_pages: test_protected_page_authenticated_flow |

### deprecated/test_two_tab_sync.py (16 tests)

| Deprecated Test | User Action | Covered By (active) |
|----------------|-------------|---------------------|
| test_two_tabs_see_same_initial_state | Two tabs see same state | **OBSOLETE** — tested CRDT text editor, not annotation |
| test_typing_in_tab1_appears_in_tab2 | Typing syncs tab1→tab2 | **OBSOLETE** — CRDT text editor |
| test_typing_in_tab2_appears_in_tab1 | Typing syncs tab2→tab1 | **OBSOLETE** — CRDT text editor |
| test_sync_happens_within_100ms | Sync latency < 100ms | **NOT COVERED** — no latency assertion in active tests |
| test_multiple_edits_all_sync | Multiple edits sync | **OBSOLETE** — CRDT text editor |
| test_alternating_edits_between_tabs | Alternating edits | **OBSOLETE** — CRDT text editor |
| test_concurrent_edits_both_visible | Concurrent edits | test_annotation_sync: test_concurrent_highlights_both_appear |
| test_empty_to_content | Empty→content syncs | **OBSOLETE** — CRDT text editor |
| test_content_to_empty | Content→empty syncs | **OBSOLETE** — CRDT text editor |
| test_unicode_content_syncs | Unicode syncs | **OBSOLETE** — CRDT text editor |
| test_long_content_syncs | Long content syncs | **OBSOLETE** — CRDT text editor |
| test_late_joiner_gets_current_state | Late joiner sees state | test_annotation_sync: test_sync_edge_cases ("late joiner") |
| test_late_joiner_can_edit | Late joiner can edit | **NOT COVERED** — late joiner editing |
| test_three_tabs_all_sync | 3-way sync | **NOT COVERED** — only 2-user tests exist |
| test_refresh_preserves_state | Refresh preserves state | test_annotation_sync: test_sync_edge_cases ("refresh preserves") |
| test_closed_tab_doesnt_break_remaining | Tab close doesn't break others | test_annotation_collab: test_user_count_updates_when_user_leaves |
| test_character_by_character_typing_syncs | Character typing syncs | **OBSOLETE** — CRDT text editor |
| test_rapid_typing_syncs | Rapid typing syncs | **OBSOLETE** — CRDT text editor |
| test_insert_at_cursor_position_syncs | Cursor position insert | **OBSOLETE** — CRDT text editor |
| test_delete_at_cursor_position_syncs | Cursor position delete | **OBSOLETE** — CRDT text editor |
| test_selection_replace_syncs | Selection replace syncs | **OBSOLETE** — CRDT text editor |

### Coverage Gaps Summary

User actions from deprecated tests that are **genuinely NOT COVERED** by active tests:

1. **Paragraph number display** (5 tests) — blocked on Issue #99 (Seam G)
2. **Tag color verification** (2 tests) — no test asserts specific tag colors
3. **Selective deletion** (1 test) — delete one highlight, verify others persist
4. **Click-without-drag = no selection** (1 test) — negative case
5. **Multiline selection** (1 test) — no cross-line selection test
6. **Key "0" applies reflection tag** (1 test) — only key "1" tested
7. **Sync latency assertion** (1 test) — no timing constraint in active tests
8. **Late joiner can edit** (1 test) — late joiner sees state but doesn't create highlights
9. **3-way sync** (1 test) — only 2-user scenarios exist

---

## Approved Decisions

1. **test_annotation_workflows.py**: Consolidate unique bits (DoD test → pdf_export), then delete
2. **test_subtests_validation.py**: Delete
3. **test_annotation_collab.py**: Keep unique only (user_count_badge x2, comment_thread_from_both_users); drop 3 duplicates
4. **Content format**: Real HTML fixtures for all reimplemented tests (not minimal `<p>` wrappers)

## Key Files

- `tests/e2e/conftest.py` — fixtures (add `clipboard_page`)
- `tests/e2e/annotation_helpers.py` — helpers (add HTML paste functions)
- `tests/e2e/helpers.py` — `click_tag()` helper (keep)
- `tests/benchmark/test_dom_performance.py` — benchmark tests (uses same `app_server` fixture)
- All 15 test files listed above + 4 deprecated files
