# Idle Tab Eviction Implementation Plan

**Goal:** Inject idle tracker and config into all `page_route`-decorated pages

**Architecture:** After client registration in the `page_route` decorator (`registry.py:302`), inject `window.__idleConfig` JSON and `<script src="/static/idle-tracker.js">` via `ui.add_head_html()` when `IDLE__ENABLED` is True. Config values converted from seconds to milliseconds for JS consumption.

**Tech Stack:** NiceGUI `ui.add_head_html()`, `json.dumps` (already in use)

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

### idle-tab-eviction-471.AC1: Server reclaims resources from idle clients
- **idle-tab-eviction-471.AC1.2 Success:** Idle eviction applies to all `page_route`-decorated pages (annotation, navigator, courses, roleplay)

### idle-tab-eviction-471.AC5: Configurable via pydantic-settings
- **idle-tab-eviction-471.AC5.3 Success:** `IDLE__ENABLED=false` disables idle eviction entirely (no script injected, no event listeners attached)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Inject idle tracker in page_route decorator

**Verifies:** idle-tab-eviction-471.AC1.2, idle-tab-eviction-471.AC5.3

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py:302-304` (add injection between `_register_client` and handler call)

**Implementation:**

After `_register_client(user_id)` (line 302) and before `await func(*args, **kwargs)` (line 304), add:

```python
idle_cfg = get_settings().idle
if idle_cfg.enabled:
    _config_json = json.dumps({
        "timeoutMs": idle_cfg.timeout_seconds * 1000,
        "warningMs": idle_cfg.warning_seconds * 1000,
        "enabled": True,
    })
    ui.add_head_html(
        f'<script>window.__idleConfig = {_config_json};</script>'
        '<script src="/static/idle-tracker.js"></script>'
        '<script>initIdleTracker();</script>'
    )
```

Add `import json` to the imports at the top of `registry.py` if not already present.

Note: `get_settings()` is already imported at line 24. The `ui` namespace is already imported. The injection is synchronous (no `await`), avoiding event-loop blocking.

**Verification:**

Run: `uv run grimoire test all`
Expected: All existing tests pass (injection is no-op in test context since NiceGUI client context won't be available)

**Complexipy check:** `uv run complexipy src/promptgrimoire/pages/registry.py` — flag if any function approaches complexity 15.

**UAT Steps:**
1. Start the app: `uv run run.py`
2. Navigate to any page_route page (e.g., `/`) while authenticated
3. Open browser DevTools → Console tab, type `window.__idleConfig`
4. Verify: should show `{timeoutMs: 1800000, warningMs: 60000, enabled: true}`
5. Open DevTools → Network tab, filter by JS
6. Verify: `idle-tracker.js` appears in loaded scripts
7. Restart app with `IDLE__ENABLED=false`
8. Repeat steps 2-6
9. Verify: `window.__idleConfig` is `undefined`, `idle-tracker.js` is NOT loaded

**Commit:** `feat(idle): inject idle tracker config and script via page_route`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for idle tracker injection

**Verifies:** idle-tab-eviction-471.AC1.2, idle-tab-eviction-471.AC5.3

**Files:**
- Create: `tests/unit/test_idle_injection.py`

**Testing:**

Test the injection logic in isolation by verifying the `page_route` decorator's behaviour with mocked NiceGUI context:

- idle-tab-eviction-471.AC1.2: With `IDLE__ENABLED=true` (default), verify that `ui.add_head_html` is called with content containing `window.__idleConfig` and `idle-tracker.js` script tag. Use `monkeypatch` to set `IDLE__ENABLED` and mock `ui.add_head_html`.

- idle-tab-eviction-471.AC5.3: With `IDLE__ENABLED=false`, verify that `ui.add_head_html` is NOT called with idle tracker content.

- Verify that the injected JSON contains correct millisecond conversion: `timeout_seconds=1800` produces `timeoutMs: 1800000`.

Follow the existing test pattern from `tests/unit/pages/test_registry.py` which mocks `ui.page()` to test decorator behaviour.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_idle_injection.py`
Expected: All tests pass

**Commit:** `test(idle): add unit tests for page_route idle injection`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
