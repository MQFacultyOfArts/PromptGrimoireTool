# Vue Annotation Sidebar Implementation Plan — Phase 1

**Goal:** Collapse Respond tab's multi-element reference cards into single `ui.html()` elements, eliminating ~3,000+ NiceGUI element constructions for 190 highlights.

**Architecture:** Replace `_build_reference_card()` (5+ NiceGUI elements per card, plus 3 per comment and 7 for long text) with a pure function `_render_reference_card_html()` that returns a single HTML string. Each card becomes one `ui.html()` call. The accordion-per-tag structure, search/filter, and refresh mechanism remain unchanged.

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

Create a pure function that renders a reference card as a single HTML string. Port the visual structure from `_build_reference_card()` (lines 112-180) into an HTML template with `html.escape()` on all interpolated values.

**HTML structure per card:**
```html
<div data-testid="respond-reference-card" style="border-left: 4px solid {color}; padding: 8px; margin-bottom: 4px;">
  <div style="display: flex; align-items: center; gap: 4px;">
    <span style="font-weight: bold; color: {color}; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{tag_display}</span>
    <span style="flex-grow: 1;"></span>
    <button data-testid="respond-locate-btn"
            onclick="scrollToCharOffset(window._textNodes, {start_char}, {end_char}); throbHighlight(window._textNodes, {start_char}, {end_char}, 800);"
            style="..." title="Locate in document">
      <span class="material-icons" style="font-size: 16px;">my_location</span>
    </button>
  </div>
  <div style="font-size: 0.85em; color: #666;">by {display_author}</div>
  <div style="font-size: 0.85em; white-space: pre-wrap; max-height: 4.5em; overflow: hidden;">{text_preview}</div>
  {para_ref_html}
  {comments_html}
</div>
```

**Key details:**
- `html.escape()` on ALL interpolated text values (tag_display, display_author, text, comment text, para_ref) — defence-in-depth XSS protection
- Locate button uses `onclick` with fire-and-forget JS — no server round-trip needed (read-only tab)
- Text preview: truncate to ~200 chars with `...` (longer than Source tab's 80 chars since this is the reference view)
- Comments: rendered as simple `<div>` blocks with author and text
- Para ref: conditional, only rendered if non-empty
- `build_expandable_text()` replaced with CSS `max-height` + `overflow: hidden` — no interactive expand/collapse needed for reference cards (keeps it to one element)

**Function signature:**
```python
def _render_reference_card_html(
    highlight: dict[str, Any],
    tag_display: str,
    color: str,
    display_author: str,
    start_char: int,
    end_char: int,
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
html_str = _render_reference_card_html(highlight, tag_display, color, display_author, start_char, end_char)
ui.html(html_str)
```

This changes each card from 5+ NiceGUI elements (card + row + labels + button) to 1 `ui.html()` element.

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

Cases:
- Basic rendering: tag display, colour, author, text present in output
- XSS escaping: `<script>` in tag_display, author, text → escaped in output
- Locate button: `onclick` contains correct `start_char` and `end_char` values
- Comments: 2 comments → both author and text present in output
- Para ref: present → rendered; absent → not rendered
- Long text: truncated with CSS `max-height` (not JS expand/collapse)
- data-testid attributes present: `respond-reference-card`, `respond-locate-btn`

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
