# Vue Annotation Sidebar Implementation Plan — Phase 8

**Goal:** Remaining card interactions: click-to-edit para_ref, locate highlight (scroll + throb), and hover highlight (already done in Phase 5).

**Architecture:** Para_ref editing uses sidebar-level `paraRefEditMode` reactive Map for client-side display↔edit toggle. Save emits `edit_para_ref` event to Python. Locate button emits `locate_highlight` event; Python fires `scrollToCharOffset` + `throbHighlight` JS (fire-and-forget).

**Tech Stack:** NiceGUI 3.9.0, Vue 3, Python 3.14

**Scope:** Phase 8 of 10 from original design

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

This phase implements and tests:

### vue-annotation-sidebar-457.AC1: Card Interactions (remaining)
- **vue-annotation-sidebar-457.AC1.8 Success:** Para_ref click enters edit mode, blur/enter saves to CRDT
- **vue-annotation-sidebar-457.AC1.9 Success:** Locate button scrolls document to highlight range with throb animation
- **vue-annotation-sidebar-457.AC1.10 Success:** Hover over card highlights text range in document

Note: AC1.10 (hover) was implemented in Phase 5 Task 3. This phase verifies it with a test.

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/cards.py:217-282` — current `_build_para_ref_editor()` (click-to-edit state machine)
- `src/promptgrimoire/pages/annotation/cards.py:414-415` — locate button JS calls (`scrollToCharOffset`, `throbHighlight`)
- `src/promptgrimoire/static/annotation-highlight.js:261-282` — `showHoverHighlight()`, `clearHoverHighlight()`, `throbHighlight()`
- `src/promptgrimoire/static/annotation-sidebar.js` — from Phase 7
- `src/promptgrimoire/pages/annotation/sidebar.py` — from Phase 7
- CLAUDE.md — fire-and-forget JS convention

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add para_ref click-to-edit to Vue component

**Verifies:** vue-annotation-sidebar-457.AC1.8

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

Add sidebar-level reactive state:
```javascript
const paraRefEditMode = reactive(new Map());  // highlightId → boolean
const paraRefDrafts = reactive(new Map());    // highlightId → draft text
```

**Template (in detail section, replacing Phase 6 placeholder):**
```html
<!-- Display mode -->
<span v-if="!paraRefEditMode.get(item.id)"
      @click="startParaRefEdit(item.id, item.para_ref)"
      data-testid="para-ref-label"
      style="cursor: pointer">
  {{ item.para_ref || '(no ref)' }}
</span>

<!-- Edit mode -->
<input v-if="paraRefEditMode.get(item.id)"
       :value="paraRefDrafts.get(item.id) ?? item.para_ref"
       @input="paraRefDrafts.set(item.id, $event.target.value)"
       @blur="finishParaRefEdit(item.id)"
       @keydown.enter="finishParaRefEdit(item.id)"
       data-testid="para-ref-input" />
```

**Methods:**
```javascript
function startParaRefEdit(id, currentValue) {
    paraRefDrafts.set(id, currentValue || '');
    paraRefEditMode.set(id, true);
    // Focus input on next tick
    nextTick(() => {
        const input = document.querySelector(`[data-highlight-id="${id}"] [data-testid="para-ref-input"]`);
        if (input) input.focus();
    });
}

function finishParaRefEdit(id) {
    const newValue = (paraRefDrafts.get(id) || '').trim();
    const item = props.items.find(i => i.id === id);
    const oldValue = item ? item.para_ref : '';
    paraRefEditMode.delete(id);
    paraRefDrafts.delete(id);
    if (newValue !== oldValue) {
        emit('edit_para_ref', { id: id, value: newValue });  // Use destructured emit from setup(props, { emit })
    }
}
```

**Key behaviour:**
- Only emits if value actually changed (prevents unnecessary CRDT mutations)
- Edit mode is per-card via Map (multiple cards can't be in edit mode simultaneously in practice, but the Map supports it)
- Blur and Enter both trigger save
- Para_ref display shown even when can_annotate is false (read-only), click-to-edit only when can_annotate

**Commit:** `feat(annotation): add para_ref click-to-edit to Vue sidebar (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add edit_para_ref Python handler

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

Register event handler:
```python
self.on('edit_para_ref', self._handle_edit_para_ref)
```

Handler (port from `cards.py:264-277`):
1. Extract `id` and `value` from `e.args`
2. `state.crdt_doc.update_highlight_para_ref(id, value)`
3. Persist workspace (`mark_dirty` + `force_persist`)
4. `state.save_status.text = "Saved"`
5. Rebuild items → push `items` prop
6. `await state.broadcast_update()`

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): add edit_para_ref Python handler for Vue sidebar (#457)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Wire locate button event

**Verifies:** vue-annotation-sidebar-457.AC1.9

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

**Vue side:** Enable locate button in compact header (from Phase 4 placeholder):
```html
<button @click="onLocate(item.start_char, item.end_char)"
        data-testid="locate-btn"
        title="Scroll to highlight">
  <span class="material-icons" style="font-size: 16px">my_location</span>
</button>
```

**`onLocate` method:**
```javascript
function onLocate(startChar, endChar) {
    this.$emit('locate_highlight', { start_char: startChar, end_char: endChar });
}
```

**Python handler:**
```python
self.on('locate_highlight', self._handle_locate_highlight)
```

Handler (port from `cards.py:414-415`):
1. Extract `start_char` and `end_char` from `e.args`
2. Fire-and-forget JS:
   ```python
   ui.run_javascript(
       f"scrollToCharOffset(window._textNodes, {start_char}, {end_char});"
       f"throbHighlight(window._textNodes, {start_char}, {end_char}, 800);"
   )
   ```

**Note:** `ui.run_javascript()` is fire-and-forget (no `await`). Per CLAUDE.md: "All `run_javascript()` calls in production code MUST be fire-and-forget."

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): wire locate button event in Vue sidebar (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration tests for para_ref, locate, and hover

**Verifies:** vue-annotation-sidebar-457.AC1.8, AC1.9, AC1.10

**Files:**
- Create: `tests/integration/test_vue_sidebar_interactions.py`

**Testing:**
NiceGUI integration test (`@pytest.mark.nicegui_ui`).

Cases to cover:
- **AC1.8 (para_ref edit):**
  - Click para-ref-label → input appears (para-ref-input visible)
  - Change value, trigger blur → label shows new value, CRDT updated
  - Change value, press Enter → same behaviour
  - No change, blur → no CRDT mutation (check CRDT state unchanged)
  - Edit mode respects `can_annotate` — non-annotators see label but click does nothing

- **AC1.9 (locate):**
  - Click locate button → `locate_highlight` event emitted with correct start_char/end_char
  - (Full scroll/throb verification requires E2E — this test verifies the event flow)

- **AC1.10 (hover):**
  - Verify hover event handlers are wired on card elements
  - (Full CSS Highlight API verification requires E2E — this test verifies the wiring)

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_interactions.py`
Expected: All tests pass

**Commit:** `test(annotation): integration tests for Vue sidebar para_ref, locate, hover (#457)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
