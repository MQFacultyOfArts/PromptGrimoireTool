# Vue Annotation Sidebar Implementation Plan — Phase 1

**Goal:** Collapse Respond tab's multi-element reference cards into single `ui.html()` elements, eliminating ~3,000+ NiceGUI element constructions for 190 highlights.

**Architecture:** Replace `_build_reference_card()` (5+ NiceGUI elements per card, plus 3 per comment and 7 for long text) with a pure function `_render_reference_card_html()` that returns an HTML string for the card body, rendered inside a wrapper `ui.element("div")`. The locate button remains a NiceGUI `ui.button` (positioned `absolute` top-right) because it requires server-side `_warp_to_highlight()` for tab switching — pure JS onclick cannot call `state.tab_panels.set_value()`. Each card becomes 3 NiceGUI elements (wrapper + html + button) instead of 8-10. The accordion-per-tag structure, search/filter, and refresh mechanism remain unchanged.

**Plan deviation (2026-03-31):** The original plan specified a single `ui.html()` with inline JS onclick for locate. This was incorrect — locate from Respond/Organise tabs must switch to the Source tab server-side via `_warp_to_highlight()`. The wrapper-plus-button architecture achieves the performance target (0.22ms/card vs 0.5ms threshold) while preserving correct tab-switching behaviour.

**Tech Stack:** NiceGUI 3.9.0, Python 3.14

**Scope:** Phase 1 of 10 from original design (prepended — Respond tab fix)

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

### vue-annotation-sidebar-457.AC8: Respond Tab Performance
- **vue-annotation-sidebar-457.AC8.1 Success:** Respond reference panel renders 190 highlights without blocking the event loop for >50ms
- **vue-annotation-sidebar-457.AC8.2 Success:** Search/filter still works (rebuild with filtered highlights)
- **vue-annotation-sidebar-457.AC8.3 Success:** Locate button on reference card switches to Source tab and scrolls to highlight

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/respond.py:112-180` — current `_build_reference_card()` (multi-element)
- `src/promptgrimoire/pages/annotation/respond.py:250-302` — `_build_reference_panel()` (accordion per tag)
- `src/promptgrimoire/pages/annotation/respond.py:776-807` — `refresh_references()` (rebuild on update)
- `src/promptgrimoire/pages/annotation/card_shared.py` — `anonymise_display_author()`, `build_expandable_text()`
- `src/promptgrimoire/pages/annotation/cards.py:318-365` — `_render_compact_header_html()` (reference pattern for HTML consolidation)
- `tests/e2e/test_law_student.py` — persona test exercising Respond tab
- CLAUDE.md — project conventions, data-testid, fire-and-forget JS

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `_render_reference_card_html()` pure function

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py`

**Implementation:**

Create a pure function that renders the card body as an HTML string, plus a wrapper function `_build_reference_card_html()` that assembles the NiceGUI elements.

**Pure function** `_render_reference_card_html()` renders the card body (tag label, author, text, para_ref, comments) as HTML. The locate button and card-level attributes (`data-testid`, border styling) are handled by the wrapper.

**Wrapper** `_build_reference_card_html()` creates:
1. `ui.element("div")` — wrapper with `data-testid="respond-reference-card"`, border styling, `position: relative`
2. `ui.html(body_html, sanitize=False)` — the pure function's output
3. `ui.button(icon="my_location")` — NiceGUI locate button, `position: absolute; top: 4px; right: 4px`, with `data-testid="respond-locate-btn"`

**Key details:**
- `html.escape()` on ALL interpolated text values — defence-in-depth XSS protection
- Locate button is a NiceGUI element (not inline JS) because it calls `_warp_to_highlight()` for server-side tab switching
- Locate button positioned `absolute` top-right to visually sit in the header area
- Text preview with CSS `max-height` + `overflow: hidden` (no interactive expand/collapse)
- Comments: rendered as simple `<div>` blocks with author and text
- Para ref: conditional, only rendered if non-empty
- Comment authors pre-anonymised before passing to pure renderer

**Pure function signature:**
```python
def _render_reference_card_html(
    *,
    tag_display: str,
    color: str,
    display_author: str,
    text: str,
    para_ref: str,
    comments: list[tuple[str, str]],
) -> str:
```

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/respond.py`
Expected: No type errors

**Commit:** `perf(annotation): consolidate Respond reference cards to single ui.html() (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Replace `_build_reference_card()` calls with `ui.html()`

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py`

**Implementation:**

In `_build_reference_panel()` (line 250-302), where `_build_reference_card()` is currently called per highlight:

Replace:
```python
_build_reference_card(highlight, tag_info, on_locate=on_locate, ...)
```

With:
```python
_build_reference_card_html(highlight, tag_colour, tag_name, state, on_locate)
```

This changes each card from 8-10 NiceGUI elements to 3 (wrapper div + html + locate button). The old `_build_reference_card()` is deleted.

**Search/filter:** `_filter_highlights()` (lines 182-227) runs before rendering — no change needed. It filters the highlight list, then the builder renders only matching highlights.

**Accordion structure:** Each tag group's `ui.expansion()` container stays as-is — it contains `ui.html()` elements instead of `ui.card()` elements.

**Refresh:** `refresh_references()` clears and rebuilds — no change to the refresh mechanism, just faster rebuilds.

**Verification:**
Run: `uv run grimoire test all`
Run: `uv run grimoire e2e run -k respond or -k law_student`
Expected: Tests pass, Respond tab renders correctly

**Commit:** `perf(annotation): wire single-element reference cards in Respond tab (#457)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Unit test for reference card HTML rendering

**Verifies:** vue-annotation-sidebar-457.AC8.1, AC8.3

**Files:**
- Create: `tests/unit/test_respond_reference_card_html.py`

**Testing:**
Pure function test — no NiceGUI, no database.

Cases (pure function only — locate button and card-level attrs tested in integration):
- Basic rendering: tag display, colour, author, text present in output
- XSS escaping: `<script>` in tag_display, author, text, comment text, comment author → escaped
- Comments: 2 comments → both author and text present; empty text → skipped
- Para ref: present → rendered; absent → not rendered
- Long text: rendered with CSS `max-height` + `overflow` (not JS expand/collapse)
- Empty text: no text div rendered
- Card-level `data-testid` NOT in body HTML (on NiceGUI wrapper instead)

**Verification:**
Run: `uv run grimoire test run tests/unit/test_respond_reference_card_html.py`
Expected: All tests pass

**Commit:** `test(annotation): unit tests for Respond reference card HTML rendering (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E verification of Respond tab with Pabai fixture

**Verifies:** vue-annotation-sidebar-457.AC8.1, AC8.2, AC8.3

**Files:**
- Verify: existing E2E tests that exercise Respond tab (`test_law_student.py`)

**Testing:**
Run existing persona tests that navigate to the Respond tab. Verify:
- Reference panel renders with highlight cards grouped by tag
- Search/filter works (type in search, cards filter)
- Locate button switches to Source tab and scrolls

If existing tests don't cover the Pabai fixture specifically, the cross-tab E2E test (Phase 10 Task 6) will exercise this with 190 highlights.

**Verification:**
Run: `uv run grimoire e2e run -k law_student`
Expected: Respond tab tests pass

**Commit:** No commit if existing tests pass. If adaptation needed: `test(annotation): adapt Respond tab E2E tests for single-element cards (#457)`
<!-- END_TASK_4 -->
