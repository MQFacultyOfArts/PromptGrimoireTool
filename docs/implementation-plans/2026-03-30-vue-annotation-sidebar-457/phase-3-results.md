# Phase 3 Spike — Go/No-Go Results

**Date:** 2026-04-02
**Verdict:** GO — proceed to Phase 4

## Go/No-Go Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Component registration works | PASS | `AnnotationSidebar(ui.element, component=_JS_PATH)` instantiates without error; NiceGUI serves the JS file |
| 2 | Python props arrive in Vue | PARTIAL — Python dict only; Vue rendering unverified until Phase 4 browser tests | `el._props["items"]` contains `[{"id": "h1"}, {"id": "h2"}]` after construction |
| 3 | Vue emits reach Python | PARTIAL — listener registration and dispatch verified; full `$emit` -> websocket -> Python path unverified until browser tests | `on("test_event", ...)` registers listener with correct type; direct dispatch delivers `{"id": "h1"}` payload |
| 4 | Prop updates re-render correctly | PARTIAL — Python dict only; Vue re-rendering unverified until Phase 4 | `set_items([{"id": "h3"}])` updates `_props["items"]` and calls `self.update()` |
| 5 | DOM exposes data-testid/data-* attributes | PASS (structural) | JS template contains `data-testid="annotation-card"` and `:data-highlight-id="item.id"` |

## Composition API Hybrid

**Result:** Structural validation PASS

The JS component uses the hybrid pattern:
- `setup(props)` with `Vue.ref()` and `Vue.watch()` (Composition API)
- `methods` and `template` (Options API)

Structural checks confirm the pattern is present. Whether Vue's runtime accepts `setup()` inside NiceGUI's component system requires browser validation (see below).

## Path Resolution

`component=Path(__file__).resolve().parent.parent.parent / "static" / "annotation-sidebar.js"` resolves correctly. NiceGUI's `register_vue_component()` accepts the path and registers the JS component.

## Testing Limitations

NiceGUI's `user_simulation` runs server-side only — no browser, no Vue runtime. The spike tests validate:
- Python-side wiring (component creation, props, events, updates)
- JS file structure (data-testid, emit pattern, Composition API usage)

**Not validated by these tests:**
- Vue actually renders the template in a browser
- `Vue.ref()` / `Vue.watch()` work inside NiceGUI's component system
- `this.$emit("test_event", ...)` reaches Python via the real websocket path
- Prop updates trigger Vue reactivity and DOM re-rendering

These are covered by Phase 4's integration tests (DOM contract) and Phase 10's cross-tab E2E tests which run in a real browser.

## Route Registration Pattern

Module-level `@ui.page()` decorators are cleared by `user_simulation`'s NiceGUI reset. Test pages must be registered inside the test function body (after the `nicegui_user` fixture establishes the simulation context). This pattern is documented in the spike test for future phases.

## Decision

Criteria 1 and 5 fully pass. Criteria 2, 3, and 4 pass at the Python-side wiring level (partial). Vue rendering and `$emit` -> websocket paths are unverified — these gaps close naturally in Phase 4 (DOM contract browser tests) and Phase 10 (cross-tab E2E in real Chromium). No blockers to proceeding.
