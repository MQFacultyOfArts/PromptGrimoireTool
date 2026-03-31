# Vue Annotation Sidebar Implementation Plan — Phase 5

**Goal:** Cards positioned absolutely aligned to document highlights. Scroll, expand/collapse, and item changes trigger repositioning with collision avoidance.

**Architecture:** Port `positionCards()` from `annotation-card-sync.js:44-83` into the Vue component. Use Vue `watch` on items prop (with `{ flush: 'post' }`) instead of MutationObserver. Keep scroll throttle via rAF. The Vue component owns its positioning lifecycle.

**Tech Stack:** NiceGUI 3.9.0, Vue 3, browser Range API, CSS Highlight API

**Scope:** Phase 5 of 10 from original design

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

### vue-annotation-sidebar-457.AC3: Overlay Positioning
- **vue-annotation-sidebar-457.AC3.1 Success:** Cards positioned absolutely aligned to highlight vertical position in document
- **vue-annotation-sidebar-457.AC3.2 Success:** Scroll, expand/collapse, and item changes trigger repositioning with collision avoidance

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/static/annotation-card-sync.js:29-111` — existing `setupCardPositioning()`, `positionCards()`, scroll listener, MutationObserver
- `src/promptgrimoire/static/annotation-highlight.js:230-237` — `charOffsetToRect()` function
- `src/promptgrimoire/static/annotation-highlight.js:33-73` — `walkTextNodes()` and `window._textNodes` setup
- `src/promptgrimoire/static/annotation-highlight.js:261-282` — `showHoverHighlight()`, `clearHoverHighlight()`, `throbHighlight()`
- `src/promptgrimoire/pages/annotation/tab_bar.py:325-332` — per-document `_positionCardsMap`
- `src/promptgrimoire/static/annotation-sidebar.js` — from Phase 4
- CLAUDE.md — fire-and-forget JS, data-testid conventions

---

<!-- START_TASK_1 -->
### Task 1: Add positionCards() method to Vue component

**Verifies:** vue-annotation-sidebar-457.AC3.1, vue-annotation-sidebar-457.AC3.2

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js` (from Phase 4)

**Implementation:**

Port the algorithm from `annotation-card-sync.js:44-83`:

1. Get text nodes: `window._textNodes` (re-walk if stale — check first node in document)
2. Get document container by `props.doc_container_id` and sidebar container by `this.$el`
3. Query cards within component root via `this.$el.querySelectorAll('[data-start-char]')`
4. For each card: parse `data-start-char`, call `charOffsetToRect(textNodes, startChar)`, cache height, compute `targetY`
5. Sort by startChar
6. Collision avoidance: monotonic `minY`, each card at `max(targetY, minY)`, increment by `height + 8`
7. Set `card.style.top = y + 'px'`

Register on window for Python fire-and-forget calls: `window._positionCards = positionCards`

**Commit:** `feat(annotation): add positionCards() to Vue sidebar component (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add scroll listener and watch trigger

**Verifies:** vue-annotation-sidebar-457.AC3.2

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

**Scroll listener** (rAF throttle, passive, in `onMounted`, cleanup in `onBeforeUnmount`).

**Items watch:** `watch(() => props.items, () => positionCards(), { flush: 'post' })` — reposition after DOM update.

**Initial positioning:** Wait for `highlights-ready` event or `window._highlightsReady` flag.

**Height caching:** `card.dataset.cachedHeight` for hidden cards (existing pattern from #284).

**Commit:** `feat(annotation): add scroll/watch positioning triggers to Vue sidebar (#457)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add hover highlight (no server round-trip)

**Verifies:** vue-annotation-sidebar-457.AC1.10

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

Add `@mouseenter="onCardHover(item)"` and `@mouseleave="onCardLeave()"` on each card.

Handlers call existing window functions directly:
```javascript
function onCardHover(item) {
    const nodes = window._textNodes;
    if (nodes) window.showHoverHighlight(nodes, item.start_char, item.end_char);
}
function onCardLeave() {
    window.clearHoverHighlight();
}
```

These are in `annotation-highlight.js:261-272`, CSS Highlight API.

**Commit:** `feat(annotation): add hover highlight to Vue sidebar cards (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add doc_container_id prop and multi-document support

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

**Python:** Add `doc_container_id` prop to `AnnotationSidebar`.

**Vue:** Use `props.doc_container_id` in `positionCards()` and for epoch tracking (`window.__cardEpochs[props.doc_container_id]`).

Register in `window._positionCardsMap[props.doc_container_id]` for tab switching.

**Commit:** `feat(annotation): add doc_container_id prop for multi-document positioning (#457)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify E2E card positioning tests pass

**Verifies:** vue-annotation-sidebar-457.AC3.1, vue-annotation-sidebar-457.AC3.2

**Files:**
- Verify: `tests/e2e/test_card_layout.py` passes unchanged (same DOM contract)

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: Card layout tests pass

**Commit:** If adaptation needed: `test(annotation): adapt card layout tests for Vue sidebar (#457)`
<!-- END_TASK_5 -->
