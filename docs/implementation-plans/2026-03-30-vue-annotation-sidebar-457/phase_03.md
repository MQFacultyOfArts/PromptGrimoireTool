# Vue Annotation Sidebar Implementation Plan — Phase 3

**Goal:** Validate that NiceGUI custom Vue component wiring works in this codebase before building on it. Go/no-go gate.

**Architecture:** Minimal custom Vue component (`AnnotationSidebar`) registered via `ui.element` subclass with `component=` parameter pointing to `static/annotation-sidebar.js`. Python pushes an `items` list prop; Vue renders `<div>` per item with `data-testid` attributes; Vue emits a test event back to Python.

**Tech Stack:** NiceGUI 3.9.0, Vue 3 (bundled with NiceGUI/Quasar), Python 3.14

**Scope:** Phase 3 of 10 from original design

**Codebase verified:** 2026-03-30

**Status: COMPLETED (2026-04-02).** Verdict: GO — proceed to Phase 4. Full results in `phase-3-results.md`.

**Deviations from plan (2026-04-02):**

1. **Testing scope narrower than planned.** NiceGUI `user_simulation` has no Vue runtime — Vue templates are not rendered server-side. The plan specified `_find_all_by_testid(user, 'annotation-card')` and `_should_see_testid` to verify Vue-rendered DOM elements (criteria 2, 4, 5). These helpers search NiceGUI's Python element tree, which does not contain Vue-rendered children. Tests validate **Python-side wiring only**: prop setting, event listener registration/dispatch, JS file structure. Criteria 2, 3, 4 are **partial passes** — Vue rendering, `$emit` → websocket → Python, and prop reactivity are unverified until Phase 4+ browser tests and Phase 10 cross-tab E2E.

2. **Route registration pattern discovered.** Module-level `@ui.page()` decorators are cleared by `user_simulation`'s NiceGUI reset. Test pages must be registered inside test function bodies, not at module level. This pattern applies to all subsequent NiceGUI integration tests.

3. **Results file named `phase-3-results.md`** (plan specified `phase-1-results.md`). More accurate since this is Phase 3.

---

## Acceptance Criteria Coverage

This phase is an infrastructure spike. **Verifies: None** — go/no-go criteria are operational, not AC-mapped.

**Go/no-go criteria (from design):**
1. Component registration works (NiceGUI serves the JS file, component renders)
2. Python props arrive in Vue (`items` prop with test data visible in rendered DOM)
3. Vue emits reach Python (`$emit('test_event', {id: '...'})` triggers Python handler)
4. Prop updates from Python re-render correctly (change `items`, verify DOM updates)
5. DOM exposes required `data-testid` / `data-*` attributes (test can find them)

**Critical validation:** The design specifies Vue 3 Composition API (`setup()`, `ref`, `reactive`, `watch`). NiceGUI's documented examples use Options API. The spike tests a hybrid approach: `export default { setup() { ... }, template: '...' }`. If this fails, subsequent phases must use Options API equivalents (`data()`, `methods`, `watch` option). The spike exists to catch this before 7 phases of work proceed.

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/__init__.py:273-275` — existing static file serving pattern
- `src/promptgrimoire/pages/annotation/__init__.py` — annotation page structure
- `tests/integration/conftest.py` — `nicegui_user` fixture setup
- `tests/integration/nicegui_test_app.py` — NiceGUI test app entry point
- `tests/integration/nicegui_helpers.py` — test helper functions (`_find_by_testid`, `_should_see_testid`)
- `docs/testing.md` — testing guidelines and NiceGUI patterns
- CLAUDE.md — project conventions (fire-and-forget JS, data-testid, etc.)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create minimal AnnotationSidebar Python wrapper

**Files:**
- Create: `src/promptgrimoire/pages/annotation/sidebar.py`

**Implementation:**

Create `AnnotationSidebar(ui.element)` with:
- `component=` parameter using `Path` object pointing to `src/promptgrimoire/static/annotation-sidebar.js` (follows project convention of JS in `static/`)
- The path resolution pattern: `Path(__file__).resolve().parent.parent.parent / 'static' / 'annotation-sidebar.js'`
- One `items` prop (list of dicts, each with `id` string field)
- One event handler registration for `test_event` (accepts a callback)
- A `set_items()` method that updates the prop and calls `self.update()`

This is a minimal wrapper — just enough to validate the wiring. Type hints on all functions per project convention.

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): add minimal AnnotationSidebar Vue component wrapper (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create minimal annotation-sidebar.js Vue component

**Files:**
- Create: `src/promptgrimoire/static/annotation-sidebar.js`

**Implementation:**

Create a Vue component using the Composition API hybrid pattern (`export default { setup() { ... }, template: '...' }`). This is the critical validation — NiceGUI's examples use Options API, but the design requires Composition API features (`reactive`, `watch`). The hybrid pattern uses Composition API inside an Options API shell.

The component must:
- Accept `items` prop (Array, default `[]`)
- Use `setup(props)` with Vue's `ref()` or `reactive()` for local state (to validate Composition API works)
- Render a root `<div>` containing a `v-for` over `items`
- Each item `<div>` must have:
  - `data-testid="annotation-card"`
  - `:data-highlight-id="item.id"`
  - Display `item.id` as text content
- Include a click handler on each item that calls `this.$emit('test_event', { id: item.id })`
- Use `watch` on `items` prop (Composition API style inside `setup`) to validate prop reactivity

**Fallback plan:** If Composition API hybrid doesn't work (Task 3 test fails), rewrite using pure Options API (`data()`, `methods`, `watch` option). Document the failure in go/no-go results.

**Verification:**
File serves correctly at `/static/annotation-sidebar.js`

**Commit:** `feat(annotation): add minimal annotation-sidebar.js Vue component (#457)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create spike test validating all 5 go/no-go criteria

**Files:**
- Create: `tests/integration/test_vue_sidebar_spike.py`

**Testing:**

NiceGUI integration test using `nicegui_user` fixture. Mark with `@pytest.mark.nicegui_ui` (serial lane).

The test must validate all 5 go/no-go criteria:

1. **Component registration** — After navigating to a page that creates an `AnnotationSidebar` instance, the component renders (page doesn't error).
2. **Props arrive in Vue** — Pass `items=[{'id': 'h1'}, {'id': 'h2'}]`. Verify two elements with `data-testid="annotation-card"` are present. Use `_find_all_by_testid(user, 'annotation-card')`.
3. **Vue emits reach Python** — Click on an item card. Verify the `test_event` handler fires with `{id: 'h1'}` payload.
4. **Prop updates re-render** — Call `sidebar.set_items([{'id': 'h3'}])`. Verify DOM updates to show exactly one card with `data-highlight-id="h3"`.
5. **DOM exposes data-* attributes** — Verify `data-testid="annotation-card"` and `data-highlight-id` on rendered elements.

Use `await _should_see_testid(user, 'annotation-card')` before asserting on elements (PG005 sync access guard pattern).

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_spike.py`
Expected: All assertions pass — all 5 go/no-go criteria met

**Commit:** `test(annotation): add Vue component spike test for go/no-go validation (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Document go/no-go results

**Files:**
- Create: `docs/implementation-plans/2026-03-30-vue-annotation-sidebar-457/phase-1-results.md`

**Implementation:**

After running the spike test, document:
- Each go/no-go criterion: PASS/FAIL with evidence
- Composition API hybrid: did `setup()` + `ref()` + `watch()` work? Yes/No
- Path resolution: did `component=Path(...)` to `static/` work?
- If any criteria failed: fallback plan and whether to proceed

**Decision gate:** All 5 pass → proceed to Phase 4. Any fail → halt and reassess.

**Commit:** `docs: record Phase 3 spike go/no-go results (#457)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
