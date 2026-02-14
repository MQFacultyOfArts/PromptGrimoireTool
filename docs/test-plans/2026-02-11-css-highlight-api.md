# Human Test Plan: CSS Custom Highlight API Migration

**Date:** 2026-02-14
**Branch:** css-highlight-api
**Implementation plan:** docs/implementation-plans/2026-02-11-css-highlight-api/

## Prerequisites

- Application running locally: `uv run python -m promptgrimoire`
- Database configured and migrated: `DATABASE_URL` set, Alembic migrations applied
- `uv run test-all` passing (unit + integration tests green)
- Chrome 105+ or Edge 105+ browser (CSS Custom Highlight API support required)
- For HV3: two separate browser windows or profiles

## Phase 1: Browser Feature Gate (HV4)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open Chrome 105+ and navigate to `http://localhost:8080/login` | Login page renders normally: email input visible, "Send Magic Link" button visible, no overlay |
| 2 | Open DevTools console (F12), run `delete CSS.highlights; window.__checkBrowserGate()` | Full-page overlay appears with "Your browser does not support features required by PromptGrimoire" |
| 3 | Read the overlay text | Lists Chrome 105+, Firefox 140+, Safari 17.2+, Edge 105+ as supported versions |
| 4 | Verify the login UI is fully obscured | Email input and magic link button are not accessible |
| 5 | Click the "Go Home" link on the overlay | Browser navigates to `/` |

## Phase 3: Highlight Visual Quality (HV1)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Log in and navigate to `/annotation` | Annotation page loads |
| 2 | Create a workspace and paste multi-paragraph text | Document renders without visible `<span>` borders or artifacts |
| 3 | Select "defendant" with mouse drag, click a tag button | Highlight appears with coloured background. Text remains readable |
| 4 | Select "New South Wales", click a different tag | Second highlight with visually distinct colour |
| 5 | Select overlapping text, apply a third tag | Overlapping region shows both highlight colours (opacity layering) |
| 6 | Inspect DOM via DevTools | No `<span class="char">` elements. Highlights via `CSS.highlights` (check `CSS.highlights.keys()`) |
| 7 | Assess visual quality | Backgrounds visible but don't obscure text. Colours distinguishable. No boundary artifacts |

## Phase 4: Scroll-Sync and Card Interaction (HV2, HV5)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Create workspace with long document, add 3-4 highlights at different positions | Cards appear in sidebar |
| 2 | Scroll document slowly top to bottom | Cards smoothly track highlight positions. No jitter or jumping |
| 3 | Scroll rapidly | Cards reposition without significant delay |
| 4 | Hover over an annotation card | Corresponding highlight receives temporary visual emphasis |
| 5 | Move mouse away from card | Hover highlight disappears cleanly |
| 6 | Click go-to button on off-screen card | Document scrolls to highlight. Brief bright flash (~800ms throb) visible |
| 7 | Assess throb animation | Noticeable but not jarring. Fades cleanly. Appropriate duration |

## Phase 5: Remote Presence (HV3)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open two browser windows, log in with different accounts | Both show annotation page |
| 2 | Window A: create workspace, note ID | Workspace created |
| 3 | Window B: navigate to same workspace | Same document content loads |
| 4 | Window A: click within document text | Window B shows coloured cursor line with A's name label |
| 5 | Assess cursor appearance | Thin, coloured, clearly visible. Name label readable |
| 6 | Window A: select text by dragging | Window B shows coloured selection highlight (distinct from annotations) |
| 7 | Window A: verify own view | No remote cursor/selection for self. Only native selection visible |
| 8 | Close Window A | Window B: cursor/selection for A disappears within seconds |

## End-to-End: Full Annotation Workflow

1. Log in, navigate to `/annotation`, create workspace
2. Paste HTML with paragraphs, list, heading
3. Confirm content type, submit
4. Verify no char-span artifacts in DOM
5. Create 3 highlights across different elements
6. Verify all in `CSS.highlights` (`Array.from(CSS.highlights.keys())`)
7. Add annotation comments to at least one highlight
8. Verify sidebar cards with correct content
9. Scroll and verify card tracking
10. Export to PDF, verify highlights and margin notes

## Human Verification Items

| ID | Criterion | Why Manual | Steps |
|----|-----------|------------|-------|
| HV1 | Highlight visual quality (AC1.1, AC1.2, AC1.5) | Colour perception, opacity, readability are subjective | Phase 3 |
| HV2 | Throb animation (AC8.3, AC8.5) | Animation timing requires human judgement | Phase 4 steps 6-7 |
| HV3 | Remote presence appearance (AC3.1, AC3.2) | Cursor/selection visual quality | Phase 5 steps 4-6 |
| HV4 | Browser gate clarity (AC4.2) | Message clarity, overlay usability | Phase 1 steps 2-5 |
| HV5 | Scroll-sync fidelity (AC8.1) | Smoothness during continuous scrolling | Phase 4 steps 2-3 |

## Traceability

| AC | Automated Test | Manual Step |
|----|---------------|-------------|
| AC1.1 | `test_highlight_rendering::test_highlights_paint_without_char_spans` | HV1 |
| AC1.2 | `test_highlight_rendering::test_multiple_tags_render_with_distinct_highlights` | HV1 |
| AC1.3 | `test_highlight_rendering::test_highlight_spans_across_block_boundaries` | -- |
| AC1.4 | `test_highlight_rendering::test_invalid_offsets_silently_skipped` | -- |
| AC1.5 | `test_highlight_rendering::test_overlapping_highlights_both_visible` | HV1 |
| AC2.1 | `test_text_selection::test_mouse_selection_produces_correct_offsets` | -- |
| AC2.2 | `test_text_selection::test_selection_across_block_boundary` | -- |
| AC2.3 | `test_text_selection::test_selection_outside_container_ignored` | -- |
| AC2.4 | `test_text_selection::test_collapsed_selection_no_event` | -- |
| AC3.1 | `test_remote_presence_e2e::test_cursor_broadcast_via_event` | HV3 |
| AC3.2 | `test_remote_presence_e2e::test_selection_visible_to_remote_user` | HV3 |
| AC3.3 | `test_remote_presence_e2e::test_disconnect_removes_remote_presence` | HV3 |
| AC3.4 | `test_remote_presence_e2e::test_own_selection_not_shown_as_remote` | HV3 |
| AC3.5 | `test_no_char_span_queries::test_no_old_presence_symbols_in_annotation_py` | -- |
| AC4.1 | `test_browser_gate::test_supported_browser_sees_login_ui` | HV4 |
| AC4.2 | `test_browser_gate::test_unsupported_browser_sees_upgrade_message` | HV4 |
| AC5.1 | `test_public_api::test_not_in_all` | -- |
| AC5.2 | `test_public_api::test_*_not_importable` | -- |
| AC5.3 | `test_public_api::TestExtractTextFromHtmlAvailable` | -- |
| AC6.1 | `test_highlight_spans.py` (existing, unmodified) | E2E step 10 |
| AC6.2 | `tests/unit/export/` (13 files) | E2E step 10 |
| AC7.1 | `test_text_walker_parity[workspace_lawlis_v_r]` | -- |
| AC7.2 | `test_text_walker_parity[workspace_edge_cases]` | -- |
| AC7.3 | `test_text_walker_parity[workspace_empty]` | -- |
| AC8.1 | -- (human-only) | HV5 |
| AC8.2 | -- (human-only) | Phase 4 steps 4-5 |
| AC8.3 | -- (human-only) | HV2 |
| AC8.4 | `test_no_char_span_queries::test_no_char_index_queries_in_annotation_py` | -- |
| AC8.5 | `test_no_char_span_queries::test_hl_throb_css_rule_uses_only_background_color` | HV2 |
