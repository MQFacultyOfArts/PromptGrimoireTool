# Vue Annotation Sidebar Implementation Plan — Phase 2

**Goal:** Collapse Organise tab's multi-element highlight cards into single `ui.html()` elements, eliminating ~3,000+ NiceGUI element constructions for 190 highlights. Preserve SortableJS drag-and-drop.

**Architecture:** Replace `_build_highlight_card()` (4+ NiceGUI elements per card, plus 3 per comment and 7 for long text) with a pure function `_render_organise_card_html()` that returns a single HTML string. Each card becomes one `ui.html()` call. The tag column structure, SortableJS wiring, scroll preservation, and Locate button remain functionally unchanged.

**Tech Stack:** NiceGUI 3.9.0, Python 3.14, SortableJS

**Scope:** Phase 2 of 10 from original design (prepended — Organise tab fix)

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

### vue-annotation-sidebar-457.AC9: Organise Tab Performance
- **vue-annotation-sidebar-457.AC9.1 Success:** Organise tab renders 190 highlights across tag columns without blocking the event loop for >50ms
- **vue-annotation-sidebar-457.AC9.2 Success:** SortableJS drag-and-drop still works (reorder within column, move between columns)
- **vue-annotation-sidebar-457.AC9.3 Success:** Locate button on organise card switches to Source tab and scrolls to highlight

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/organise.py:50-128` — current `_build_highlight_card()` (multi-element)
- `src/promptgrimoire/pages/annotation/organise.py:172-233` — `_build_tag_column()` (SortableJS container)
- `src/promptgrimoire/pages/annotation/organise.py:236-323` — `render_organise_tab()` (main render)
- `src/promptgrimoire/pages/annotation/organise.py:131-169` — `_render_ordered_cards()` (respects drag order)
- `src/promptgrimoire/pages/annotation/tab_bar.py:210-277` — `_on_organise_sort_end()` (SortableJS event handler)
- `src/promptgrimoire/pages/annotation/tab_bar.py:52-97` — `_parse_sort_end_args()` (event parsing, relies on `hl-{id}` HTML ID)
- `src/promptgrimoire/pages/annotation/tab_bar.py:160-207` — scroll preservation JS
- `src/promptgrimoire/pages/annotation/card_shared.py` — shared utilities
- Phase 1 — reference for HTML consolidation pattern
- CLAUDE.md — project conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `_render_organise_card_html()` pure function

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py`

**Implementation:**

Create a pure function that renders an organise card as a single HTML string. Port the visual structure from `_build_highlight_card()` (lines 50-128).

**Critical SortableJS contract:**
- The `ui.html()` element's root `<div>` must have:
  - `id="hl-{highlight_id}"` — SortableJS uses this to identify dragged elements. `_parse_sort_end_args()` strips the `hl-` prefix to get the highlight ID.
  - `data-highlight-id="{highlight_id}"` — used in event parsing
- The card must have `cursor: grab` styling for drag affordance
- Locate button must have class `sortable-ignore` to prevent drag interference

**HTML structure per card:**
```html
<div id="hl-{highlight_id}" data-highlight-id="{highlight_id}" data-testid="organise-card"
     style="border-left: 4px solid {color}; padding: 8px; margin-bottom: 4px; cursor: grab;">
  <div style="display: flex; align-items: center; gap: 4px;">
    <span style="font-weight: bold; color: {color}; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{tag_display}</span>
    <span style="flex-grow: 1;"></span>
    <button class="sortable-ignore" data-testid="organise-locate-btn"
            onclick="scrollToCharOffset(window._textNodes, {start_char}, {end_char}); throbHighlight(window._textNodes, {start_char}, {end_char}, 800);"
            style="..." title="Locate in document">
      <span class="material-icons" style="font-size: 16px;">my_location</span>
    </button>
  </div>
  <div style="font-size: 0.85em; color: #666;">by {display_author}</div>
  <div style="font-size: 0.85em; white-space: pre-wrap; max-height: 4.5em; overflow: hidden;">{text_preview}</div>
  {comments_html}
</div>
```

**Key details:**
- `html.escape()` on ALL interpolated text — XSS defence-in-depth
- `id="hl-{highlight_id}"` is **not** escaped (UUID, safe) — SortableJS parses it
- Locate button with `onclick` (fire-and-forget JS, no round-trip)
- `sortable-ignore` class on Locate button prevents it from initiating drag
- Comments as simple `<div>` blocks (no interactive delete — Organise is read + reorder only)
- Text preview with CSS `max-height` (no interactive expand/collapse)
- `data-testid="organise-card"` preserved
- `data-testid="organise-locate-btn"` added (was missing in current implementation)

**Function signature:**
```python
def _render_organise_card_html(
    highlight: dict[str, Any],
    highlight_id: str,
    tag_display: str,
    color: str,
    display_author: str,
    start_char: int,
    end_char: int,
) -> str:
```

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/organise.py`
Expected: No type errors

**Commit:** `perf(annotation): consolidate Organise cards to single ui.html() (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Replace `_build_highlight_card()` calls with `ui.html()`

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py`

**Implementation:**

In `_render_ordered_cards()` (lines 131-169) and anywhere `_build_highlight_card()` is called:

Replace the NiceGUI card construction with:
```python
html_str = _render_organise_card_html(highlight, highlight_id, tag_display, color, display_author, start_char, end_char)
ui.html(html_str)
```

**SortableJS compatibility:**
- SortableJS is initialised on the column container via `ui.run_javascript()` (in `_build_tag_column()`)
- It operates on child elements of the container, using their `id` attribute for identification
- `ui.html()` renders a `<div>` — SortableJS can drag it as long as `id="hl-{id}"` is on the root element
- **Test this carefully:** SortableJS's `onEnd` event fires with `evt.item.id` — verify this still works when the dragged element is a `ui.html()` child rather than a `ui.card()` child
- `_parse_sort_end_args()` in `tab_bar.py:52-97` parses `evt.item.id` by stripping `hl-` prefix — this should work unchanged since the `id` attribute is preserved

**Column structure:** `_build_tag_column()` (lines 172-233) creates the column container and initialises SortableJS. The container stays as `ui.column()` — only the card children change to `ui.html()`.

**Scroll preservation:** The JS in `tab_bar.py:160-207` saves/restores scroll position by element ID — should work unchanged since `ui.html()` elements are standard DOM elements.

**Verification:**
Run: `uv run grimoire test all`
Run: `uv run grimoire e2e run -k organise`
Expected: Tests pass, drag-and-drop works

**Commit:** `perf(annotation): wire single-element cards in Organise tab (#457)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Unit test for organise card HTML rendering

**Verifies:** vue-annotation-sidebar-457.AC9.1, AC9.2, AC9.3

**Files:**
- Create: `tests/unit/test_organise_card_html.py`

**Testing:**
Pure function test — no NiceGUI, no database.

Cases:
- Basic rendering: tag display, colour, author, text present in output
- **SortableJS contract:** `id="hl-{highlight_id}"` present on root element
- **SortableJS contract:** `data-highlight-id="{highlight_id}"` present
- **SortableJS contract:** Locate button has `class="sortable-ignore"`
- XSS escaping: `<script>` in tag_display, author, text → escaped
- Locate button: `onclick` contains correct `start_char` and `end_char`
- Comments: rendered with author and text
- data-testid: `organise-card`, `organise-locate-btn` present

**Verification:**
Run: `uv run grimoire test run tests/unit/test_organise_card_html.py`
Expected: All tests pass

**Commit:** `test(annotation): unit tests for Organise card HTML rendering (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E verification of Organise tab — drag-and-drop regression

**Verifies:** vue-annotation-sidebar-457.AC9.1, AC9.2, AC9.3

**Files:**
- Verify: existing E2E tests that exercise Organise tab drag-and-drop

**Testing:**
Run existing tests. The critical verification is SortableJS:
- Drag a card from one tag column to another → CRDT updated with new tag
- Reorder cards within a tag column → order preserved on refresh
- Locate button clicks work (switch to Source tab, scroll)

**If SortableJS breaks with `ui.html()` children:**
The root cause would be that `ui.html()` wraps content in an extra `<div>` that breaks SortableJS's child element detection. If this happens:
- Option A: Use `ui.html(html_str).props('id=hl-{id}')` to set the id on the wrapper
- Option B: Use `content=` parameter if available to inject without wrapper
- Option C: Adjust `_parse_sort_end_args()` to handle the wrapper

**Verification:**
Run: `uv run grimoire e2e run -k organise`
Expected: Drag-and-drop works, Locate works, tag columns correct

**Commit:** No commit if existing tests pass. If adaptation needed: `test(annotation): adapt Organise tab E2E tests for single-element cards (#457)`
<!-- END_TASK_4 -->
