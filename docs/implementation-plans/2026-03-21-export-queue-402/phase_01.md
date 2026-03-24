# PDF Export Queue Implementation Plan — Phase 1

**Goal:** Permanently fix NiceGUI's aggressive 3s client deletion on slow page loads by raising `response_timeout` to 60s.

**Architecture:** Single parameter addition to `page_route` decorator in `registry.py`. All pages using `@page_route` inherit the change.

**Tech Stack:** NiceGUI `ui.page()` `response_timeout` parameter

**Scope:** 1 of 6 phases from original design (Phase 1)

**Codebase verified:** 2026-03-21

---

## Acceptance Criteria Coverage

This phase implements and tests:

### export-queue-402.AC5: response_timeout fix (#377)
- **export-queue-402.AC5.1 Success:** `page_route` decorator passes `response_timeout=60` to `ui.page()`
- **export-queue-402.AC5.2 Edge:** Page handler taking >3s but <60s completes normally without client deletion

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add response_timeout=60 to page_route decorator

**Verifies:** export-queue-402.AC5.1

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py:175`

**Implementation:**

Change line 175 from:

```python
return ui.page(route)(_with_log_context)
```

to:

```python
return ui.page(route, response_timeout=60)(_with_log_context)
```

This is a single-line change. The `response_timeout` parameter is keyword-only on `ui.page()` and accepts a `float`. The default is `3.0` — we raise it to `60` permanently per #377 Finding 6.

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `fix: raise page_route response_timeout to 60s (#377 Finding 6)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit test for response_timeout parameter passing

**Verifies:** export-queue-402.AC5.1, export-queue-402.AC5.2

**Files:**
- Modify: `tests/unit/pages/test_registry.py`

**Testing:**

Tests must verify each AC listed above:
- export-queue-402.AC5.1: Patch `ui.page` and verify `page_route` calls it with `response_timeout=60`
- export-queue-402.AC5.2: Verify the timeout value is 60 (not the default 3.0), confirming handlers taking >3s won't trigger client deletion

The test should:
1. Patch `nicegui.ui.page` to capture the kwargs it receives
2. Call `page_route("/test-route")` with a dummy handler
3. Assert `response_timeout=60` was passed to `ui.page()`

Follow existing patterns in `tests/unit/pages/test_registry.py`. This is a sync test (no database, no async).

**Verification:**

Run: `uv run grimoire test run tests/unit/pages/test_registry.py`
Expected: All tests pass including the new test

**Commit:** `test: verify page_route passes response_timeout=60 (#377)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Phase Verification

Run: `uv run complexipy src/promptgrimoire/pages/registry.py --max-complexity-allowed 15`
Expected: No functions exceed threshold

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Navigate to an annotation workspace with a large document
3. [ ] Verify the page loads without client deletion (previously failed for loads >3s)
4. [ ] Run tests: `uv run grimoire test run tests/unit/pages/test_registry.py`

## Evidence Required
- [ ] Test output showing response_timeout test passes
- [ ] App starts without errors
