# Bottom-Anchored Tag Bar Implementation Plan — Phase 4

**Goal:** Add above/below flip logic to the highlight menu positioning so it avoids the bottom toolbar, and bump the menu's z-index above the toolbar.

**Architecture:** Extend the existing JS positioning code in `annotation-highlight.js` with a boundary check that flips the menu above the selection when it would overlap the bottom toolbar. Bump z-index from `z-50` to `z-[110]` in the Python-side menu builder.

**Tech Stack:** Vanilla JavaScript, NiceGUI (Python), Tailwind CSS

**Scope:** 5 phases from original design (phase 4 of 5)

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### bottom-tag-bar.AC3: Highlight menu positioned near selection
- **bottom-tag-bar.AC3.1 Success:** Selecting text in upper/middle viewport shows highlight menu below the selection (default position)
- **bottom-tag-bar.AC3.2 Success:** Menu left edge aligns with the end of the selection
- **bottom-tag-bar.AC3.3 Success:** Selecting text near viewport bottom shows highlight menu above the selection (flipped), using actual toolbar height for threshold
- **bottom-tag-bar.AC3.4 Failure:** Menu never renders behind or overlapping the bottom toolbar, even when toolbar wraps to multiple rows
- **bottom-tag-bar.AC3.5 Success:** Highlight menu z-index (110) renders above toolbar (100) if positions ever overlap
- **bottom-tag-bar.AC3.6 Edge:** Selecting text at very top of viewport — menu stays below selection even if that's the overlap zone (z-index handles it)

---

## Reference Files

The executor should read these for project context:
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/CLAUDE.md` — Project conventions
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/docs/annotation-architecture.md` — Annotation page package structure

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add flip logic to highlight menu positioning

**Verifies:** bottom-tag-bar.AC3.1, bottom-tag-bar.AC3.2, bottom-tag-bar.AC3.3, bottom-tag-bar.AC3.4, bottom-tag-bar.AC3.6

**Files:**
- Modify: `src/promptgrimoire/static/annotation-highlight.js:338-343` (menu positioning logic)

**Implementation:**

In `src/promptgrimoire/static/annotation-highlight.js`, the positioning block at lines 338-343 currently reads:

```javascript
            var menu = document.getElementById('highlight-menu');
            if (menu) {
                var endRect = charOffsetToRect(textNodes, Math.max(endChar - 1, startChar));
                menu.style.top = endRect.bottom + 8 + 'px';
                menu.style.left = endRect.left + 'px';
            }
```

Replace the positioning lines (keeping the `var menu` and `if (menu)` structure) with:

```javascript
            var menu = document.getElementById('highlight-menu');
            if (menu) {
                var endRect = charOffsetToRect(textNodes, Math.max(endChar - 1, startChar));
                // 120px: conservative upper bound for highlight menu height
                // (actual ~80-100px); over-estimates to prefer above-selection on first display
                var menuH = menu.offsetHeight || 120;
                var toolbarH = window._toolbarHeight || 60;
                var topPos = endRect.bottom + 8;

                // Flip above selection if menu would overlap bottom toolbar
                if (topPos + menuH > window.innerHeight - toolbarH) {
                    var flipped = endRect.top - menuH - 8;
                    // Only flip if the flipped position stays on-screen (AC3.6)
                    if (flipped >= 0) {
                        topPos = flipped;
                    }
                    // If flipped goes off-screen too (selection at very top),
                    // keep below-selection — z-index (110 > 100) handles overlap
                }

                menu.style.top = topPos + 'px';
                menu.style.left = endRect.left + 'px';
            }
```

Key details:
- `menu.offsetHeight || 120` — after first show, `offsetHeight` returns actual rendered height. On very first selection (menu is `display: none`), falls back to 120px conservative estimate.
- `window._toolbarHeight || 60` — reads actual toolbar height from ResizeObserver (Phase 1). Falls back to 60px if not set.
- Flip condition: `topPos + menuH > window.innerHeight - toolbarH` — if menu bottom would extend below the toolbar top edge, flip to above selection.
- Edge case (AC3.6): if flipping would put the menu above the viewport (`flipped < 0`), keep below-selection positioning. The z-index bump (Task 2) ensures the menu renders above the toolbar if they overlap.
- `endRect.left` for the left position is unchanged (AC3.2 — menu left edge aligns with selection end).

**Verification:**

Start the app: `uv run python -m promptgrimoire`
Navigate to an annotation workspace with content.
1. Select text in the middle of the page — menu should appear below the selection.
2. Select text near the bottom of the viewport — menu should flip to above the selection.
3. Select text at the very top — menu stays below (even if that overlaps the toolbar area, z-index handles it).

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace with content
3. [ ] Select text in the middle of the page
4. [ ] Verify: highlight menu appears below the selection (AC3.1)
5. [ ] Verify: menu left edge aligns with end of selection (AC3.2)
6. [ ] Scroll down and select text near the bottom of the viewport (within ~150px of the toolbar)
7. [ ] Verify: highlight menu flips to above the selection (AC3.3)
8. [ ] Verify: menu does not overlap or render behind the bottom toolbar (AC3.4)

**Commit:** `feat: add above/below flip logic to highlight menu positioning`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Bump highlight menu z-index above toolbar

**Verifies:** bottom-tag-bar.AC3.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document.py:164` (z-index class on highlight menu card)

**Implementation:**

In `src/promptgrimoire/pages/annotation/document.py`, the `_build_highlight_menu()` function at line 162-164:

```python
    highlight_menu = (
        ui.card()
        .classes("fixed z-50 shadow-lg p-2")
```

Change `z-50` to `z-[110]`:

```python
    highlight_menu = (
        ui.card()
        .classes("fixed z-[110] shadow-lg p-2")
```

This sets `z-index: 110`, which is above the toolbar's `z-index: 100` (set in Phase 1 via `css.py:372`). If the menu and toolbar ever occupy the same screen area (e.g., the AC3.6 edge case), the menu renders on top.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/document.py`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace
3. [ ] Open DevTools, inspect the highlight menu element (`#highlight-menu`)
4. [ ] Verify: computed `z-index` is `110` (above toolbar's `100`) (AC3.5)

**Commit:** `feat: bump highlight menu z-index above toolbar`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
