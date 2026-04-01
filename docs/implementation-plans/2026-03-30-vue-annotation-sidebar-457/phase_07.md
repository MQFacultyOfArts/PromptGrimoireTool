# Vue Annotation Sidebar Implementation Plan — Phase 7

**Goal:** All CRDT-mutating interactions work through Vue events → Python handlers → prop updates. Tag change, comment add/delete, highlight delete.

**Architecture:** Vue component emits semantic events (`change_tag`, `submit_comment`, `delete_comment`, `delete_highlight`) with payloads. Python handlers mutate CRDT, persist to DB, broadcast to other clients, and push updated `items` prop. Permission gating is client-side (hide controls) + server-side (CRDT auth rejects unauthorised mutations).

**Tech Stack:** NiceGUI 3.9.0, Vue 3, Python 3.14, pycrdt

**Scope:** Phase 7 of 10 from original design

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

This phase implements and tests:

### vue-annotation-sidebar-457.AC1: Card Interactions (partial)
- **vue-annotation-sidebar-457.AC1.4 Success:** Tag dropdown change updates card border colour and CRDT
- **vue-annotation-sidebar-457.AC1.5 Success:** Comment submit adds comment to list, clears input, increments badge
- **vue-annotation-sidebar-457.AC1.6 Success:** Comment delete removes comment, decrements badge
- **vue-annotation-sidebar-457.AC1.7 Success:** Highlight delete removes card from sidebar and CRDT
- **vue-annotation-sidebar-457.AC1.11 Failure:** Comment submit with empty/whitespace text is rejected (no CRDT mutation)
- **vue-annotation-sidebar-457.AC1.12 Edge:** Tag dropdown shows recovery entry when highlight references deleted tag

### vue-annotation-sidebar-457.AC4: Permissions
- **vue-annotation-sidebar-457.AC4.1 Success:** Users with `can_annotate` see tag dropdown, comment input, and post button
- **vue-annotation-sidebar-457.AC4.2 Failure:** Viewers without `can_annotate` do not see edit controls
- **vue-annotation-sidebar-457.AC4.4 Failure:** Unauthorized mutation event (crafted `delete_highlight` as viewer) rejected server-side, no CRDT change
- **vue-annotation-sidebar-457.AC4.3 Success:** Delete buttons shown only for content owner or privileged user

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/cards.py:284-315` — `_make_tag_change_handler()` (tag change logic)
- `src/promptgrimoire/pages/annotation/cards.py:145-187` — `_make_add_comment_handler()` (comment add logic)
- `src/promptgrimoire/pages/annotation/cards.py:75-118` — comment delete handler
- `src/promptgrimoire/pages/annotation/highlights.py:187-217` — `_delete_highlight()` (highlight delete logic)
- `src/promptgrimoire/pages/annotation/broadcast.py:333-358` — `_handle_remote_update()` (broadcast handling)
- `src/promptgrimoire/pages/annotation/broadcast.py:361-454` — `_setup_client_sync()` (broadcast setup)
- `src/promptgrimoire/ui_helpers.py:25-77` — `on_submit_with_value()` pattern (NOT needed in Vue — reference only)
- `src/promptgrimoire/crdt/annotation_doc.py:315-337` — `update_highlight_tag()`
- `src/promptgrimoire/crdt/annotation_doc.py:682-726` — `add_comment()`
- `src/promptgrimoire/crdt/annotation_doc.py:728-779` — `delete_comment()` (with server-side auth)
- `src/promptgrimoire/pages/annotation/sidebar.py` — from Phase 6
- `src/promptgrimoire/static/annotation-sidebar.js` — from Phase 6
- CLAUDE.md — fire-and-forget JS, permission model

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Wire tag change event in Vue component

**Verifies:** vue-annotation-sidebar-457.AC1.4, vue-annotation-sidebar-457.AC1.12

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

Enable the tag dropdown in the detail section (remove `disabled` from Phase 6):

```html
<select v-if="permissions.can_annotate"
        data-testid="tag-select"
        :value="item.tag_key"
        @change="onTagChange(item.id, $event.target.value)">
  <option v-for="(name, key) in tagOptions" :key="key" :value="key">{{ name }}</option>
  <!-- Recovery entry for deleted tags -->
  <option v-if="!tagOptions[item.tag_key]"
          :value="item.tag_key">⚠ recovered</option>
</select>
```

**`onTagChange(id, newTag)` method:**
```javascript
function onTagChange(id, newTag) {
    // Emit to Python handler
    this.$emit('change_tag', { id: id, new_tag: newTag });
}
```

**Immediate visual update:** Update the card's border colour client-side without waiting for the prop round-trip. Look up the colour from `tagOptions` and a colour map (or add a `tag_colours` prop to pass hex values). This gives instant feedback while the CRDT mutation propagates.

**Commit:** `feat(annotation): wire tag change event in Vue sidebar (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add change_tag Python handler

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

Register event handler:
```python
self.on('change_tag', self._handle_change_tag)
```

Handler logic (port from `cards.py:284-315`):
1. Extract `id` and `new_tag` from `e.args` payload
2. `state.crdt_doc.update_highlight_tag(id, new_tag)`
3. `pm.mark_dirty_workspace()` + `await pm.force_persist_workspace()`
4. `state.save_status.text = "Saved"`
5. `_update_highlight_css(state)` — rebuild CSS Highlight API entries
6. Rebuild items and push updated `items` prop
7. `await state.broadcast_update()` — notify other clients

**Note:** Unlike the current implementation which updates a single card's border inline style, the Vue component receives the updated colour via the items prop and re-renders. The instant visual update is handled client-side in Vue (Task 1).

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): add change_tag Python handler for Vue sidebar (#457)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Wire comment CRUD events in Vue component

**Verifies:** vue-annotation-sidebar-457.AC1.5, vue-annotation-sidebar-457.AC1.6, vue-annotation-sidebar-457.AC1.11

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

**Comment input and post button** (enable from Phase 6 placeholder):
```html
<template v-if="permissions.can_annotate">
  <input v-model="commentDrafts.get(item.id) ?? ''"
         @input="commentDrafts.set(item.id, $event.target.value)"
         data-testid="comment-input"
         placeholder="Add a comment..." />
  <button @click="onSubmitComment(item.id)"
          data-testid="post-comment-btn">Post</button>
</template>
```

**`commentDrafts`:** Sidebar-level `reactive(new Map())` — maps highlight ID → draft text. Local until submit.

**`onSubmitComment(id)` method:**
```javascript
function onSubmitComment(id) {
    const text = (commentDrafts.get(id) || '').trim();
    if (!text) return;  // AC1.11: reject empty/whitespace
    this.$emit('submit_comment', { id: id, text: text });
    commentDrafts.set(id, '');  // Clear draft immediately (optimistic)
}
```

**Comment delete buttons:**
```html
<button v-if="comment.can_delete"
        @click="onDeleteComment(item.id, comment.id)"
        data-testid="comment-delete">×</button>
```

**`onDeleteComment(highlightId, commentId)` method:**
```javascript
function onDeleteComment(highlightId, commentId) {
    this.$emit('delete_comment', { highlight_id: highlightId, comment_id: commentId });
}
```

**Note:** `reactive(new Map())` in Vue 3 is fully reactive — `.set()` and `.delete()` trigger re-renders. The template uses `:value` + `@input` bindings (not `v-model`) because `v-model` doesn't bind to Map entries directly.

**Commit:** `feat(annotation): wire comment CRUD events in Vue sidebar (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add comment CRUD Python handlers

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

Register event handlers:
```python
self.on('submit_comment', self._handle_submit_comment)
self.on('delete_comment', self._handle_delete_comment)
```

**Submit comment handler** (port from `cards.py:145-187`):
1. Extract `id` and `text` from `e.args`
2. Validate: `if not text or not text.strip(): return` (AC1.11 server-side defence)
3. `state.crdt_doc.add_comment(id, state.user_name, text.strip(), user_id=state.user_id)`
4. Persist workspace
5. Rebuild items → push `items` prop
6. `await state.broadcast_update()`

**Delete comment handler** (port from `cards.py:75-118`):
1. Extract `highlight_id` and `comment_id` from `e.args`
2. `deleted = state.crdt_doc.delete_comment(highlight_id, comment_id, requesting_user_id=state.user_id, is_privileged=state.viewer_is_privileged)`
3. If `not deleted: return` (server-side auth rejected)
4. Persist workspace
5. Rebuild items → push `items` prop
6. `await state.broadcast_update()`

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): add comment CRUD Python handlers for Vue sidebar (#457)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Wire highlight delete event

**Verifies:** vue-annotation-sidebar-457.AC1.7, vue-annotation-sidebar-457.AC4.3

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

**Vue side:** Enable delete button in compact header (from Phase 4 placeholder):
```html
<button v-if="item.can_delete"
        @click="onDeleteHighlight(item.id)"
        data-testid="highlight-delete-btn">
  <span class="material-icons" style="font-size: 16px">close</span>
</button>
```

**Python handler** (port from `highlights.py:187-217`):
1. Extract `id` from `e.args`
2. **Server-side auth check (authoritative):** Look up the highlight from CRDT: `hl = state.crdt_doc.get_highlight(id)`. If `hl` is None, return (already deleted). Check permission: `is_own = state.user_id is not None and hl.get("user_id") == state.user_id`. If not `is_own` and not `state.viewer_is_privileged`, return (unauthorised — defence-in-depth, client-side `can_delete` already hides the button but a crafted event could bypass Vue).
3. `state.crdt_doc.remove_highlight(id)`
4. Persist workspace
5. `_update_highlight_css(state)` — remove from CSS Highlight API
6. Clean up: remove from `state.expanded_cards`, `state.detail_built_cards` if present
7. Rebuild items → push `items` prop (card disappears from Vue's render)
8. `await state.broadcast_update()`

**Note:** Unlike the current implementation which calls `card.delete()` on a NiceGUI element, the Vue component simply stops rendering the card when it's removed from the `items` prop. Vue's reactivity handles DOM cleanup.

**Permission gating:** `item.can_delete` is pre-computed server-side in `serialise_items()` (Phase 4). Vue conditionally renders the delete button. CRDT's `remove_highlight()` does not have server-side auth (unlike `delete_comment()`), so the Python handler should add a permission check before calling the CRDT method.

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): wire highlight delete event in Vue sidebar (#457)`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration tests for CRDT mutations and permissions

**Verifies:** vue-annotation-sidebar-457.AC1.4, AC1.5, AC1.6, AC1.7, AC1.11, AC1.12, AC4.1, AC4.2, AC4.3, AC4.4

**Files:**
- Create: `tests/integration/test_vue_sidebar_mutations.py`

**Testing:**
NiceGUI integration test (`@pytest.mark.nicegui_ui`) using Pabai fixture.

Cases to cover:
- **AC1.4:** Change tag on a highlight → CRDT updated, card colour changes, tag_display changes
- **AC1.5:** Submit comment → comment appears in card, badge count increments, input clears
- **AC1.6:** Delete comment → comment removed, badge count decrements
- **AC1.7:** Delete highlight → card removed from sidebar
- **AC1.11:** Submit empty/whitespace comment → no mutation, comment list unchanged
- **AC1.12:** Highlight with deleted tag → dropdown shows "⚠ recovered" entry
- **AC4.1:** User with can_annotate sees tag-select, comment-input, post-comment-btn
- **AC4.2:** User without can_annotate does NOT see tag-select, comment-input, post-comment-btn
- **AC4.3:** Own content shows delete button, others' content does not (unless privileged)
- **AC4.4:** Emit `delete_highlight` event as viewer (no can_delete permission) → Python handler rejects, CRDT state unchanged, highlight still exists

Test permission by creating sidebar with different `permissions` and `can_delete` flags.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_mutations.py`
Expected: All tests pass

**Commit:** `test(annotation): integration tests for Vue sidebar CRDT mutations and permissions (#457)`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->
