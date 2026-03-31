# Vue Annotation Sidebar Implementation Plan — Phase 6

**Goal:** Cards expand to show detail section on click. Detail built lazily on first expand. Pre-expanded cards render with detail visible.

**Architecture:** Vue component manages `expandedIds` (reactive Set) and `detailBuiltIds` (reactive Set) at sidebar level, keyed by highlight ID. On first expand, detail DOM is created (`v-if`). On subsequent toggles, visibility toggled (`v-show`). Python receives `toggle_expand` event and updates `expanded_ids` prop (server-authoritative for reconnection).

**Tech Stack:** NiceGUI 3.9.0, Vue 3, Python 3.14

**Scope:** Phase 6 of 10 from original design

**Codebase verified:** 2026-03-31

---

## Acceptance Criteria Coverage

### vue-annotation-sidebar-457.AC1: Card Interactions (partial)
- **vue-annotation-sidebar-457.AC1.1 Success:** Clicking header row expands card, detail section visible
- **vue-annotation-sidebar-457.AC1.2 Success:** Clicking expanded header collapses card, detail hidden but retained
- **vue-annotation-sidebar-457.AC1.3 Success:** Cards in `expanded_ids` render with detail visible on load

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/cards.py:485-625` — current lazy detail, expand/collapse
- `src/promptgrimoire/pages/annotation/card_shared.py:53-80` — `build_expandable_text()`
- `src/promptgrimoire/pages/annotation/__init__.py:248-253` — `expanded_cards`, `detail_built_cards`
- `tests/integration/test_lazy_card_detail.py` — existing lazy detail tests (AC1.1-AC1.3)
- CLAUDE.md — conventions

---

## Prerequisite: Deduplicate Pabai fixture

Two copies exist:
- `tests/e2e/fixtures/pabai_workspace.json` — un-scrubbed (PII, must be BFG'd)
- `tests/integration/fixtures/workspace_pabai_190hl_scrubbed.json` — PII-scrubbed (keep)

**Action:** Move scrubbed copy to `tests/fixtures/pabai_workspace_scrubbed.json`, update all imports, delete un-scrubbed copy. BFG for git history is a separate manual operation.

---

<!-- START_TASK_1 -->
### Task 1: Deduplicate Pabai fixture

**Files:**
- Move: `tests/integration/fixtures/workspace_pabai_190hl_scrubbed.json` → `tests/fixtures/pabai_workspace_scrubbed.json`
- Delete: `tests/e2e/fixtures/pabai_workspace.json`
- Modify: `tests/integration/test_memory_leak_probe.py`, `tests/e2e/test_session_contamination.py`, `tests/e2e/test_memory_probe_434.py`, `tests/e2e/test_browser_perf_377.py` — update paths

**Commit:** `chore: deduplicate Pabai fixture, remove PII copy (#457)`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Add expand/collapse and lazy detail to Vue component

**Verifies:** vue-annotation-sidebar-457.AC1.1, vue-annotation-sidebar-457.AC1.2, vue-annotation-sidebar-457.AC1.3

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

Sidebar-level reactive state:
- `expandedIds: reactive(new Set())` — currently expanded
- `detailBuiltIds: reactive(new Set())` — cards with detail rendered

**Initialise from props:** Populate `expandedIds` from `props.expanded_ids` on mount.

**Chevron button:** `@click="toggleExpand(item.id)"`, icon toggles `expand_more`/`expand_less`.

**Detail section:**
```html
<div v-if="detailBuiltIds.has(item.id)"
     v-show="expandedIds.has(item.id)"
     data-testid="card-detail">
  <!-- Tag dropdown (disabled until Phase 7) -->
  <select v-if="permissions.can_annotate" data-testid="tag-select" disabled>
    <option v-for="(name, key) in tag_options" :key="key" :value="key"
            :selected="key === item.tag_key">{{ name }}</option>
    <option v-if="!tag_options[item.tag_key]" :value="item.tag_key">⚠ recovered</option>
  </select>
  <div>by {{ item.display_author }}</div>
  <div>{{ item.text_preview }}</div>
  <div v-if="item.para_ref" data-testid="para-ref-label">{{ item.para_ref }}</div>
  <div v-for="comment in item.comments" :key="comment.id" data-testid="comment">
    <span data-testid="comment-author">{{ comment.author }}</span>
    <span>{{ comment.text }}</span>
  </div>
  <span data-testid="comment-count">{{ item.comments.length }}</span>
  <template v-if="permissions.can_annotate">
    <input data-testid="comment-input" disabled />
    <button data-testid="post-comment-btn" disabled>Post</button>
  </template>
</div>
```

**`toggleExpand(id)`:** Add/remove from `expandedIds` + `detailBuiltIds`, emit `toggle_expand`, trigger `positionCards()` via `$nextTick`.

**Optimistic:** Vue expands immediately; Python confirms via prop update (no-op if already correct).

**Commit:** `feat(annotation): add expand/collapse and lazy detail to Vue sidebar (#457)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add toggle_expand event handler to Python sidebar

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

Handler receives `{id, expanded}` → update `state.expanded_cards` → push updated `expanded_ids` prop.

**Commit:** `feat(annotation): add toggle_expand Python handler for Vue sidebar (#457)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Integration test for expand/collapse and lazy detail

**Verifies:** vue-annotation-sidebar-457.AC1.1, vue-annotation-sidebar-457.AC1.2, vue-annotation-sidebar-457.AC1.3

**Files:**
- Create: `tests/integration/test_vue_sidebar_expand.py`

**Testing:**
NiceGUI integration test (`@pytest.mark.nicegui_ui`) with Pabai fixture.

Cases:
- AC1.1: Click header → detail visible
- AC1.2: Click expanded header → detail hidden, retained in DOM
- AC1.3: `expanded_ids=['id1']` → detail visible on initial render
- Lazy: collapsed card has no `card-detail` in DOM; after expand, it exists; after collapse, still there
- Repositioning fires after expand (cards below shift)

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_expand.py`
Expected: All tests pass

**Commit:** `test(annotation): integration tests for Vue sidebar expand/collapse (#457)`
<!-- END_TASK_4 -->
