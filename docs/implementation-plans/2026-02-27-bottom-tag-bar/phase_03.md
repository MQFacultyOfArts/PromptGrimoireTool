# Bottom-Anchored Tag Bar Implementation Plan — Phase 3

**Goal:** Update annotation card sync boundaries to account for toolbar moving from top to bottom.

**Architecture:** Modify the viewport boundary constants in the card positioning function to remove the top dead zone (toolbar is no longer at top) and add a bottom dead zone (toolbar is now at bottom, height read from `window._toolbarHeight`).

**Tech Stack:** Vanilla JavaScript

**Scope:** 5 phases from original design (phase 3 of 5)

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase is infrastructure. The design plan mapped AC3.1 and AC3.2 to this phase, but those ACs describe highlight menu behaviour (Phase 4). Card sync boundary changes have no direct ACs — they are operationally verified.

**Verifies: None** (operational verification target OP1: annotation cards near viewport bottom are visible above the toolbar, not hidden behind it)

---

## Reference Files

The executor should read these for project context:
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/CLAUDE.md` — Project conventions

---

<!-- START_TASK_1 -->
### Task 1: Update card sync viewport boundaries

**Verifies:** None (infrastructure — operationally verified via OP1: cards above toolbar visible near viewport bottom)

**Files:**
- Modify: `src/promptgrimoire/static/annotation-card-sync.js:63` (boundary constants)

**Implementation:**

In `src/promptgrimoire/static/annotation-card-sync.js`, the `positionCards()` inner function (inside `setupCardPositioning()`) has viewport boundary constants at line 63:

```javascript
// BEFORE:
var hH = 60, vT = hH, vB = window.innerHeight;
```

Change to:

```javascript
// AFTER:
var hH = 0, vT = hH, vB = window.innerHeight - (window._toolbarHeight || 60);
```

Changes:
1. `hH = 60` → `hH = 0` — no top obstruction (toolbar moved to bottom). `vT` becomes 0, so cards at the very top of the viewport are visible.
2. `vB = window.innerHeight` → `vB = window.innerHeight - (window._toolbarHeight || 60)` — bottom boundary shrinks by toolbar height. Cards whose highlights extend entirely below this line are hidden. The `|| 60` fallback covers the case where `window._toolbarHeight` hasn't been set yet by the ResizeObserver (Phase 1).

The visibility check at line 71 is unchanged:
```javascript
var inView = er.bottom > vT && sr.top < vB;
```

Since `positionCards()` is called on every scroll event, `vB` is recalculated each time with the current `window._toolbarHeight` value.

**Verification:**

Start the app: `uv run python -m promptgrimoire`
Navigate to an annotation workspace with multiple annotations.
Scroll to the bottom of the document. Annotation cards near the bottom should be fully visible above the toolbar. They should not be hidden behind the toolbar.
Scroll to the top. Annotation cards at the very top of the viewport should be visible (no 60px dead zone).

**UAT Steps:**
1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: an annotation workspace with multiple highlights/annotations
3. [ ] Scroll to the bottom of the document
4. [ ] Verify: annotation cards near the bottom are fully visible above the toolbar — not hidden behind it (OP1)
5. [ ] Scroll to the very top
6. [ ] Verify: annotation cards at the top of the viewport are visible (no 60px dead zone from old toolbar position)

**Commit:** `feat: update card sync boundaries for bottom toolbar`
<!-- END_TASK_1 -->
