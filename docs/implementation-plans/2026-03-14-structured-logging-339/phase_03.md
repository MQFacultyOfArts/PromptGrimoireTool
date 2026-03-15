# Structured Logging Implementation Plan — Phase 3

**Goal:** Automatic `user_id`, `workspace_id`, `request_path` on every log line within a request context.

**Architecture:** `structlog.contextvars` for async-safe per-request context binding. Two injection layers: page_route decorator (user_id, request_path) and workspace setup points (workspace_id).

**Tech Stack:** structlog.contextvars, NiceGUI app.storage.user

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### structured-logging-339.AC1: Log lines carry request context
- **structured-logging-339.AC1.1 Success:** Log line from an authenticated page handler contains `user_id`, `request_path`, `pid`, `branch`, `commit`
- **structured-logging-339.AC1.2 Success:** Log line from an annotation workspace handler additionally contains `workspace_id`
- **structured-logging-339.AC1.3 Success:** `jq 'select(.workspace_id == "XXX")' logs/promptgrimoire.jsonl` returns all events for that workspace
- **structured-logging-339.AC1.4 Edge:** Log line from unauthenticated page (e.g. login) has `user_id: null` but still has `pid`, `branch`, `commit`, `request_path`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Enhance page_route decorator with context binding

**Verifies:** structured-logging-339.AC1.1, structured-logging-339.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py` (lines 74-122, the `page_route` decorator)

**Implementation:**

Modify the `page_route` decorator to wrap the handler function with context binding. The wrapper should:

1. Import `structlog.contextvars` (bind_contextvars, clear_contextvars) at the top of registry.py.

2. In the `decorator` inner function, create a wrapper around `func` that:
   a. Calls `clear_contextvars()` to prevent context leaking from previous page navigations (critical for NiceGUI WebSocket model where a single connection navigates between pages)
   b. Resolves auth user: `auth_user = app.storage.user.get("auth_user")`
   c. Extracts user_id: `user_id = auth_user.get("user_id") if auth_user else None`
   d. Calls `bind_contextvars(user_id=user_id, request_path=route)`
   e. Calls the original `func()` with `await` (page handlers are async)

3. Use `functools.wraps(func)` on the wrapper to preserve the original function signature.

4. Pass the wrapper (not func) to `ui.page(route)` on line 120.

The route string is available in the decorator closure — use it directly as `request_path` (not `client.request.url` which requires awaiting connection).

**Testing:**

Tests must verify:
- structured-logging-339.AC1.1: A page handler log call produces JSON with `user_id`, `request_path`, `pid`, `branch`, `commit`
- structured-logging-339.AC1.4: An unauthenticated page handler log call produces JSON with `user_id: null` but `request_path` still present

Follow project testing patterns. Task-implementor generates actual test code at execution time. Note: Testing context propagation through the decorator may require mocking `app.storage.user` — check existing test patterns in `tests/unit/test_config.py` for monkeypatch approach.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/registry.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: enhance page_route decorator with structlog context binding`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Bind workspace_id at workspace setup points

**Verifies:** structured-logging-339.AC1.2, structured-logging-339.AC1.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py` (after line 372 in `_setup_client_sync()`)
- Modify: `src/promptgrimoire/pages/roleplay.py` (in `roleplay_page()` and export flow)
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py` (in `_handle_pdf_export()`)

**Implementation:**

Add `bind_contextvars(workspace_id=str(workspace_id))` at each workspace resolution point:

1. **`broadcast.py:_setup_client_sync()`** — After line 372 (after `client_user_id` resolution), add:
   ```python
   from structlog.contextvars import bind_contextvars
   bind_contextvars(workspace_id=str(workspace_id))
   ```
   This is the primary injection point — all annotation workspace operations flow through here.

2. **`roleplay.py:roleplay_page()`** — After `await ui.context.client.connected()` and auth checks, bind user context. When a workspace is created during export (around line 232), additionally bind workspace_id.

3. **`annotation/pdf_export.py:_handle_pdf_export()`** — At function entry, bind workspace_id:
   ```python
   from structlog.contextvars import bind_contextvars
   bind_contextvars(workspace_id=str(workspace_id))
   ```
   This ensures the entire export pipeline (which runs in Phase 5) inherits workspace context.

Convert workspace_id to string with `str()` since UUID objects aren't JSON-serialisable by default.

**Testing:**

Tests must verify:
- structured-logging-339.AC1.2: A log call within an annotation workspace handler contains `workspace_id`
- structured-logging-339.AC1.3: Multiple log events for the same workspace all share the same `workspace_id` value (queryable by jq)

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/broadcast.py src/promptgrimoire/pages/roleplay.py src/promptgrimoire/pages/annotation/pdf_export.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: bind workspace_id context at workspace setup points`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Integration test for context propagation

**Verifies:** structured-logging-339.AC1.1, structured-logging-339.AC1.2, structured-logging-339.AC1.3, structured-logging-339.AC1.4

**Files:**
- Modify: `tests/unit/test_structured_logging.py` (add context propagation tests)

**Implementation:**

Add tests that verify context propagation works end-to-end:

1. **Test authenticated context:** Call `bind_contextvars(user_id="test-user-123", request_path="/courses")`, then log via structlog logger, read the log file, verify JSON contains `user_id: "test-user-123"` and `request_path: "/courses"`.

2. **Test unauthenticated context:** Call `clear_contextvars()` (no bind), then log, verify JSON contains `user_id: null` and `request_path: null`.

3. **Test workspace context:** Call `bind_contextvars(workspace_id="ws-uuid-456")`, then log, verify JSON contains `workspace_id: "ws-uuid-456"`.

4. **Test context isolation:** Call `bind_contextvars(workspace_id="ws-1")`, then `clear_contextvars()`, then `bind_contextvars(user_id="user-2")`, then log. Verify JSON contains `user_id: "user-2"` and `workspace_id: null` (cleared).

These tests use structlog.contextvars directly without NiceGUI — they verify the structlog configuration from Phase 1 correctly merges contextvars into log output.

**Testing:**

- structured-logging-339.AC1.1: Verify authenticated context fields present
- structured-logging-339.AC1.2: Verify workspace_id present when bound
- structured-logging-339.AC1.3: Verify workspace_id consistent across multiple log calls
- structured-logging-339.AC1.4: Verify unauthenticated context has null user_id

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_structured_logging.py`
Expected: All tests pass

**Commit:** `test: verify structlog context propagation`

<!-- END_TASK_3 -->

## UAT Steps

1. Start the app: `uv run run.py`
2. Log in and navigate to `/courses`
3. Run: `tail -1 logs/promptgrimoire*.jsonl | jq '.user_id, .request_path'` — should show your user ID and `"/courses"`
4. Navigate to an annotation workspace
5. Run: `jq 'select(.workspace_id != null)' logs/promptgrimoire*.jsonl | tail -1 | jq '.workspace_id, .user_id, .request_path'` — should show workspace UUID, user ID, and `"/annotation"`
6. Run: `jq 'select(.workspace_id == "YOUR-WORKSPACE-UUID")' logs/promptgrimoire*.jsonl` — should filter to only that workspace's events
7. Navigate back to `/courses` — check that the next log line has `workspace_id: null` (context cleared)
8. Log out and navigate to login page — check log line has `user_id: null` but `request_path` present
