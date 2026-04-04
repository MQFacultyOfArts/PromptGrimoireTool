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

## E2E Browser Validation (added retroactively)

The initial spike test design (NiceGUI `user_simulation` integration tests) was **insufficient for go/no-go validation**. The human identified this gap and requested Playwright E2E tests. The browser tests discovered three showstopper bugs that the integration tests could not catch:

1. **JS filename hyphens break NiceGUI's `import()`** — `annotation-sidebar.js` caused `"Unexpected token '-'"` in the browser. Renamed to `annotationsidebar.js`.
2. **`position: absolute` without `top`/`left` produces zero-size invisible cards** — cards rendered but had no visible area. Removed positioning entirely (Phase 5 will add it with computed values).
3. **NiceGUI websocket requires an authenticated session** — unauthenticated page loads produce a blank white page (Vue never mounts).

After fixing these bugs and adding E2E tests (`tests/e2e/test_vue_sidebar_spike_e2e.py`), all 5 criteria pass at the browser level:
- GO1: Component renders in Chromium (2 cards as real DOM nodes)
- GO2: Props arrive as `data-highlight-id`, `data-start-char`, tag labels, initials, comment badges
- GO3: Vue `$emit("test_event")` reaches Python handler via websocket (full round-trip confirmed)
- GO4: `set_items()` from Python re-renders Vue component (2 cards → 1 card)
- GO5: All `data-testid` and `data-*` attributes present in DOM

## Decision

Criteria 1-5 now pass at the E2E browser level. The original integration-only test design was inadequate for the stated go/no-go purpose — it validated Python wiring but could not catch the three integration bugs listed above. Proceed to Phase 4.
