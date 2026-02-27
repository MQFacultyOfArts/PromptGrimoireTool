# Bottom-Anchored Tag Bar Implementation Plan — Phase 1

**Goal:** Move the tag toolbar from viewport-top to viewport-bottom with dynamic height tracking via ResizeObserver.

**Architecture:** CSS repositioning of existing toolbar wrapper, compact button specificity fix, and a new ResizeObserver in `annotation-card-sync.js` that dynamically sets layout padding and exposes toolbar height for downstream consumers.

**Tech Stack:** NiceGUI (Python), Tailwind CSS, vanilla JavaScript (ResizeObserver API)

**Scope:** 5 phases from original design (phase 1 of 5)

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### bottom-tag-bar.AC1: Tag toolbar anchored to bottom
- **bottom-tag-bar.AC1.1 Success:** Toolbar renders at `position: fixed; bottom: 0` with full viewport width
- **bottom-tag-bar.AC1.2 Success:** Box-shadow appears above the toolbar (upward shadow), not below
- **bottom-tag-bar.AC1.3 Success:** Document content below the fold is not hidden behind the toolbar (padding-bottom dynamically matches toolbar height)
- **bottom-tag-bar.AC1.4 Success:** Toolbar with many tags wrapping to multiple rows — padding-bottom adjusts automatically via ResizeObserver, no content obscured

### bottom-tag-bar.AC4: Compact button padding fix
- **bottom-tag-bar.AC4.1 Success:** Compact buttons render with `padding: 0px 6px` (not Quasar's `2px 8px`)

---

## Reference Files

The executor should read these for project context:
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/CLAUDE.md` — Project conventions and commands
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/docs/testing.md` — Test guidelines, E2E patterns
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/docs/annotation-architecture.md` — Annotation page package structure

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Flip toolbar CSS and fix compact button specificity

**Verifies:** bottom-tag-bar.AC1.1, bottom-tag-bar.AC1.2, bottom-tag-bar.AC4.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/css.py:368-375` (toolbar wrapper inline style)
- Modify: `src/promptgrimoire/pages/annotation/css.py:178-183` (compact button CSS rule)

**Implementation:**

In `src/promptgrimoire/pages/annotation/css.py`, the `_build_tag_toolbar()` function (starts at line 340) creates the toolbar wrapper at lines 368-375:

```python
toolbar_wrapper = (
    ui.element("div")
    .classes("bg-gray-100 py-1 px-4")
    .style(
        "position: fixed; top: 0; left: 0; right: 0; z-index: 100; "
        "box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
    )
)
```

Change to:

```python
toolbar_wrapper = (
    ui.element("div")
    .classes("bg-gray-100 py-1 px-4")
    .props('id="tag-toolbar-wrapper"')
    .style(
        "position: fixed; bottom: 0; left: 0; right: 0; z-index: 100; "
        "box-shadow: 0 -2px 4px rgba(0,0,0,0.1);"
    )
)
```

Changes:
1. Added `.props('id="tag-toolbar-wrapper"')` — provides a stable DOM ID for ResizeObserver targeting in Task 3
2. `top: 0` → `bottom: 0` — anchors toolbar to viewport bottom
3. `box-shadow: 0 2px 4px` → `box-shadow: 0 -2px 4px` — shadow projects upward instead of downward

In the same file, the compact button CSS rule at lines 178-183:

```css
.compact-btn {
    padding: 2px 8px !important;
    min-height: 24px !important;
    font-size: 11px !important;
    vertical-align: middle !important;
}
```

Change selector and padding:

```css
.q-btn.compact-btn {
    padding: 0px 6px !important;
    min-height: 24px !important;
    font-size: 11px !important;
    vertical-align: middle !important;
}
```

Changes:
1. `.compact-btn` → `.q-btn.compact-btn` — higher specificity beats Quasar's `.q-btn` default padding
2. `padding: 2px 8px` → `padding: 0px 6px` — tighter padding per design spec

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/css.py`
Expected: No lint errors

Run: `uv run ruff format --check src/promptgrimoire/pages/annotation/css.py`
Expected: No format changes needed

Run: `uvx ty check`
Expected: No type errors

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace
3. [ ] Verify: tag toolbar appears at the bottom of the viewport, not the top (AC1.1)
4. [ ] Verify: toolbar shadow appears above the bar (subtle upward shadow), not below (AC1.2)
5. [ ] Verify: compact tag buttons have tighter padding than default Quasar buttons (AC4.1)

**Commit:** `feat: flip tag toolbar to bottom of viewport and fix compact button specificity`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update layout wrapper padding and add ID

**Verifies:** bottom-tag-bar.AC1.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document.py:223-227` (layout wrapper inline style)

**Implementation:**

In `src/promptgrimoire/pages/annotation/document.py`, the layout wrapper at lines 223-227:

```python
layout_wrapper = ui.element("div").style(
    "position: relative; display: flex; gap: 1.5rem; "
    "width: 90%; max-width: 1600px; margin: 0 auto; padding-top: 60px; "
    "min-height: calc(100vh - 250px);"
)
```

Change to:

```python
layout_wrapper = (
    ui.element("div")
    .props('id="annotation-layout-wrapper"')
    .style(
        "position: relative; display: flex; gap: 1.5rem; "
        "width: 90%; max-width: 1600px; margin: 0 auto; padding-bottom: 60px; "
        "min-height: calc(100vh - 250px);"
    )
)
```

Changes:
1. Added `.props('id="annotation-layout-wrapper"')` — provides a stable DOM ID for ResizeObserver to update `padding-bottom`
2. `padding-top: 60px` → `padding-bottom: 60px` — padding shifts from top (old toolbar position) to bottom (new toolbar position). The initial 60px is a conservative fallback. ResizeObserver in Task 3 fires synchronously on first observation, replacing this value before paint in most browsers; a 1-frame layout shift on cold load is expected and acceptable if the toolbar renders at a different height.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/document.py`
Expected: No lint errors

Run: `uv run ruff format --check src/promptgrimoire/pages/annotation/document.py`
Expected: No format changes needed

Run: `uvx ty check`
Expected: No type errors

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace with content that extends below the fold
3. [ ] Verify: document content at the bottom is not hidden behind the toolbar (AC1.3)
4. [ ] Scroll to the very bottom — last paragraph should be fully visible above the toolbar

**Commit:** `feat: switch layout padding from top to bottom for bottom toolbar`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Add ResizeObserver for dynamic toolbar height tracking

**Verifies:** bottom-tag-bar.AC1.3, bottom-tag-bar.AC1.4

**Files:**
- Modify: `src/promptgrimoire/static/annotation-card-sync.js` (add ResizeObserver block, approximately near the top of the file or after the existing initialization)

**Implementation:**

In `src/promptgrimoire/static/annotation-card-sync.js`, add a ResizeObserver that:
1. Observes the toolbar wrapper element (`#tag-toolbar-wrapper`)
2. On resize: reads the toolbar's `offsetHeight`, stores it in `window._toolbarHeight`
3. Updates the layout wrapper's `padding-bottom` to match (`#annotation-layout-wrapper`)

Add the following block at the end of the file (or after the existing `syncCards` initialisation):

```javascript
// --- ResizeObserver: track toolbar height for layout padding + card sync ---
(function initToolbarObserver() {
  var toolbar = document.getElementById('tag-toolbar-wrapper');
  var layout  = document.getElementById('annotation-layout-wrapper');
  if (!toolbar || !layout) return;

  var ro = new ResizeObserver(function(entries) {
    for (var i = 0; i < entries.length; i++) {
      var h = entries[i].target.offsetHeight;
      window._toolbarHeight = h;
      layout.style.paddingBottom = h + 'px';
    }
  });
  ro.observe(toolbar);
})();
```

Key details:
- `window._toolbarHeight` is a global read by card sync (Phase 3) and highlight menu (Phase 4)
- The IIFE pattern matches existing code style in this file (no ES modules, var declarations)
- `offsetHeight` includes borders and padding — matches what content needs to avoid
- The ResizeObserver fires immediately on first observation, so the initial 60px fallback from Task 2 is replaced with the actual height within one frame

**Verification:**

Start the app: `uv run python -m promptgrimoire`
Navigate to an annotation workspace. Open browser DevTools console.
Run: `window._toolbarHeight` — should return a number (likely ~40-60px).
Run: `document.getElementById('annotation-layout-wrapper').style.paddingBottom` — should match.

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace with many tags (enough to wrap the toolbar to 2+ rows)
3. [ ] Verify: `window._toolbarHeight` in DevTools console returns a positive number
4. [ ] Verify: the layout padding adjusts when toolbar wraps — content at the bottom is never hidden behind the taller toolbar (AC1.4)
5. [ ] Resize the window narrower to force tag wrapping — padding should adjust dynamically

**Commit:** `feat: add ResizeObserver for dynamic toolbar height tracking`
<!-- END_TASK_3 -->
