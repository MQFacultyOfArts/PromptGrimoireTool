# Annotation Deferred Load — Phase 2: Deferred Page Load

**Goal:** Transform the annotation page from a blocking handler (3+ seconds) to a skeleton-first pattern that returns in <50ms, with content populated asynchronously via a background task.

**Architecture:** `annotation_page()` renders a minimal skeleton (page layout shell + spinner) and schedules content loading via `background_tasks.create()`. The background task uses `resolve_annotation_context()` (from Phase 1), builds the UI inside `with client:`, then hides the spinner.

**Tech Stack:** NiceGUI `background_tasks.create()`, `with client:` context manager, Playwright E2E tests.

**Scope:** Phase 2 of 4 from original design.

**Codebase verified:** 2026-03-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### annotation-deferred-load-377.AC1: Page handler returns immediately
- **annotation-deferred-load-377.AC1.1:** `annotation_page()` handler completes in <50ms (measured via responseEnd in Performance API)
- **annotation-deferred-load-377.AC1.2:** Loading spinner is visible to the user before DB work begins (Playwright: spinner element visible before `__loadComplete`)
- **annotation-deferred-load-377.AC1.3:** NiceGUI "Response not ready after 3.0 seconds" warning does not appear for annotation page loads under normal conditions

### annotation-deferred-load-377.AC3: Progressive hydration
- **annotation-deferred-load-377.AC3.1:** After background task completes, spinner is hidden and workspace content is visible
- **annotation-deferred-load-377.AC3.2:** If background task fails (DB error, timeout), user sees error notification — not infinite spinner
- **annotation-deferred-load-377.AC3.3:** If client disconnects during DB work, background task is cancelled via `client.on_disconnect` handler AND exits early at yield points via `client._deleted` guard (belt-and-suspenders: `on_disconnect` attempts immediate cancellation, `_deleted` guard catches cases where the task is between yield points)

### annotation-deferred-load-377.AC5: Minimal annotation UI module changes
- **annotation-deferred-load-377.AC5.1:** Only `__init__.py` and `workspace.py` are modified in `pages/annotation/`
- **annotation-deferred-load-377.AC5.2:** `cards.py`, `document.py`, `highlights.py`, `organise.py`, `respond.py`, `tab_bar.py` (if present from #186) are unchanged

---

## Reference Files

The task-implementor should read these files for context:

- **Page handler:** `src/promptgrimoire/pages/annotation/__init__.py:338-392` (annotation_page function)
- **Main render:** `src/promptgrimoire/pages/annotation/workspace.py:829-931` (_render_workspace_view)
- **Context resolution:** `src/promptgrimoire/pages/annotation/workspace.py:367-451` (_resolve_workspace_context)
- **Tab builder:** `src/promptgrimoire/pages/annotation/workspace.py:676-785` (_build_tab_panels)
- **Client sync:** `src/promptgrimoire/pages/annotation/broadcast.py:322-413` (_setup_client_sync)
- **Background tasks set:** `src/promptgrimoire/pages/annotation/__init__.py:198` (_background_tasks)
- **with client: pattern:** `src/promptgrimoire/pages/annotation/__init__.py:127-129` (_RemotePresence.invoke_callback)
- **Page route decorator:** `src/promptgrimoire/pages/registry.py` (page_route, response_timeout)
- **Testing patterns:** `docs/testing.md`, `.ed3d/implementation-plan-guidance.md`
- **E2E test patterns:** `tests/e2e/` (Playwright tests with data-testid locators)

---

<!-- START_TASK_0 -->
### Task 0: Spike — verify background_tasks.create() + with client: combination

**Verifies:** None (infrastructure — validates architectural assumption before committing)

**Files:**
- No production files modified (spike only)

**Implementation:**

The design identifies an unverified assumption: `background_tasks.create()` wrapping an async function that uses `with client:` for UI updates has not been tested in this codebase. This spike validates the combination before committing to the architecture.

Create a minimal test page (can be a temporary file or an inline test):
1. Create an async page handler that renders a label "Loading..."
2. Schedule a background task via `background_tasks.create()`
3. Inside the background task, sleep briefly (simulate DB work), then use `with client:` to update the label text to "Done"
4. Verify the label text changes from "Loading..." to "Done"

**Fallback:** If the combination fails (e.g., `RuntimeError: slot stack empty`), fall back to `ui.timer(0, once=True)` which runs in the client context automatically and doesn't need `with client:`. Update Tasks 1-2 accordingly.

**Verification:**
Run the spike. If the label changes to "Done" without errors, proceed with Tasks 1-2 using `background_tasks.create()` + `with client:`.

**Commit:** None (spike only — delete test page after verification)

<!-- END_TASK_0 -->

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Restructure annotation_page to render skeleton and schedule background task

**Verifies:** annotation-deferred-load-377.AC1.1, annotation-deferred-load-377.AC1.2, annotation-deferred-load-377.AC5.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` (annotation_page function at line 338)

**Implementation:**

Transform `annotation_page()` to render a minimal skeleton and schedule content loading. The current function blocks on `_render_workspace_view()` — change it to render immediately and defer all DB work.

**Current flow (blocking):**
```
annotation_page() →
  _setup_page_styles() →
  parse workspace_id →
  await get_workspace(workspace_id) →      # DB call 1
  page_layout() →
  await _render_workspace_view(...)         # DB calls 2-10, full UI build
```

**New flow (deferred):**
```
annotation_page() →
  _setup_page_styles() →
  parse workspace_id →
  page_layout() →
  render spinner inside content area →
  background_tasks.create(_load_workspace_content(...))  # Returns immediately
```

Key changes:
1. Remove the pre-fetch `await get_workspace(workspace_id)` — the background task will fetch it via `resolve_annotation_context()`.
2. Inside `page_layout()`, create a container `div` and a `ui.spinner()` inside it. Give the spinner a `data-testid="workspace-loading-spinner"` for E2E tests.
3. Import `background_tasks` from `nicegui` and call `background_tasks.create()` with the async content loader coroutine. **Store the returned task handle.**
4. Pass `client`, `workspace_id`, the spinner element, and the content container to the background task.
5. **Wire `client.on_disconnect` to cancel the task:** `client.on_disconnect(lambda: task.cancel())`. This provides best-effort immediate cancellation when the client navigates away during loading. Note: `on_disconnect` fires asynchronously so the task may already be between yield points — combine with `client._deleted` guard inside the task (belt-and-suspenders).
6. The "no workspace_id" branch (create workspace form) remains synchronous — it's fast and has no DB calls.

**Import to add:**
```python
from nicegui import background_tasks
```

**The response_timeout in registry.py can be reduced back from 60s to the default** once deferred loading is in place, but leave that for Phase 4 measurement to confirm.

**Verification:**
Run: `uv run python -c "from promptgrimoire.pages.annotation import annotation_page; print('OK')"`
Expected: `OK` (no import errors)

**Commit:** `feat(annotation): render skeleton page with deferred content loading`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement _load_workspace_content background task

**Verifies:** annotation-deferred-load-377.AC1.1, annotation-deferred-load-377.AC3.1, annotation-deferred-load-377.AC3.2, annotation-deferred-load-377.AC3.3, annotation-deferred-load-377.AC5.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (replace or refactor _render_workspace_view)
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` (if _load_workspace_content lives here)

**Implementation:**

Create `_load_workspace_content()` — an async function that runs as a background task. It replaces the blocking `_render_workspace_view()` call.

**Function responsibilities:**

1. **DB work (outside `with client:`):**
   - Call `resolve_annotation_context(workspace_id, user_id, is_admin=is_admin)` from Phase 1.
   - If returns `None` (workspace not found): show error notification via `with client:`, hide spinner, return.
   - If permission is `None` (no access): show access denied via `with client:`, hide spinner, return.
   - Call `list_documents(workspace_id)` — cache result on PageState for `@ui.refreshable` reuse.
   - Hydrate CRDT: call `_workspace_registry.get_or_create_for_workspace(workspace_id, workspace=context.workspace)` passing pre-fetched workspace.
   - Call `_ensure_crdt_tag_consistency(doc, workspace_id, tags=context.tags, tag_groups=context.tag_groups)` passing pre-fetched tags.

2. **`client._deleted` guard (belt-and-suspenders with `on_disconnect` from Task 1):** After each yield point (DB call), check `if client._deleted: return`. The `on_disconnect` handler (Task 1, step 5) provides immediate cancellation, but this guard catches cases where the task is between yield points when `on_disconnect` fires. The codebase already uses this pattern at `__init__.py:127`. Note: `_deleted` is an internal NiceGUI attribute (not public API), but the codebase has established usage — follow the existing pattern at `__init__.py:127`.

3. **UI build (inside `with client:`):**
   - Enter `with client:` context.
   - Build PageState from resolved context (currently done in `_resolve_workspace_context`).
   - Call the existing rendering functions: `render_workspace_header()`, tab building, `_build_tab_panels()`.
   - These functions remain unchanged — they receive the same data, just from the background task instead of the synchronous handler.
   - After rendering is complete, hide the spinner and show the content container.

4. **Error handling:** Wrap the entire function in `try/except Exception`. On failure:
   - `with client:` → `ui.notify("Failed to load workspace", type="negative")` → hide spinner.
   - Log the exception via `logger.exception()`.

**Key architectural constraint:** The rendering functions (`render_workspace_header`, `_build_tab_panels`, etc.) must not be modified. They are called from within `with client:` which establishes the correct UI slot context. The only change is WHERE they're called from (background task vs synchronous handler).

**Signal for E2E testing:** After content is fully rendered, set `window.__loadComplete = true` via `ui.run_javascript("window.__loadComplete = true")`. This allows Playwright to wait for content without polling DOM elements.

**Refactoring _render_workspace_view:**
The existing `_render_workspace_view()` can be refactored into `_load_workspace_content()` by:
1. Moving the DB calls to the top (outside `with client:`).
2. Using `resolve_annotation_context()` instead of individual DB function calls.
3. Wrapping the UI-building section in `with client:`.
4. Adding `client._deleted` guards at yield points.
5. Adding error handling wrapper.

The timing instrumentation (currently in `_render_workspace_view` lines 844-921) should be preserved — it's valuable for measuring the improvement.

**Verification:**
Run: `uv run run.py` (start app locally)
Navigate to an annotation workspace. Observe:
- Spinner appears immediately
- Content loads after a short delay
- No "Response not ready" warnings in server logs

**Commit:** `feat(annotation): implement deferred content loading via background task`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->

<!-- START_TASK_3 -->
### Task 3: Wire documents cache on PageState

**Verifies:** Structural — eliminates duplicate `list_documents()` call (DB session #10 from design plan). Contributes to overall session reduction (10 -> 2-3).

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (PageState usage, @ui.refreshable document container)

**Implementation:**

The `@ui.refreshable` document container at `workspace.py:730` currently calls `list_documents(workspace_id)` on every refresh — this is the duplicate call #10 from the design plan. Instead, cache the result on PageState.

1. Add a `documents` field to PageState (or use an existing field — check what `refresh_documents` currently stores).
2. In `_load_workspace_content()`, after calling `list_documents()`, store the result on `state.documents`.
3. In the `@ui.refreshable` function, read `state.documents` instead of calling `list_documents()` again.
4. When documents are added/removed (which triggers refresh), update `state.documents` before calling the refreshable.

**Key constraint:** This must work with the existing `@ui.refreshable` decorator pattern. The refreshable function should read from `state.documents` (already resolved) rather than making a new DB call.

**Verification:**
Run: `uv run grimoire test changed`
Expected: Existing tests pass

**Commit:** `perf(annotation): cache documents list on PageState`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: E2E test for deferred page load

**Verifies:** annotation-deferred-load-377.AC1.2, annotation-deferred-load-377.AC3.1, annotation-deferred-load-377.AC3.2

**Files:**
- Create: `tests/e2e/test_deferred_load.py`
- Read (reference): existing E2E tests in `tests/e2e/` for patterns

**Testing:**

Tests verify the skeleton-first loading pattern:

- **annotation-deferred-load-377.AC1.2 (spinner visible before content):** Navigate to annotation page. Assert `page.get_by_test_id("workspace-loading-spinner")` is visible. Wait for `window.__loadComplete` via `page.wait_for_function("() => window.__loadComplete === true")`. Assert spinner is no longer visible and workspace content is present.

- **annotation-deferred-load-377.AC3.1 (content appears after load):** After `__loadComplete`, verify workspace header, tab panels, and document content are visible using existing data-testid locators.

- **annotation-deferred-load-377.AC3.2 (error handling):** Navigate to annotation page with an invalid workspace_id (random UUID). Assert that after a brief delay, an error notification appears and spinner is hidden. (This tests the "workspace not found" path.)

- **annotation-deferred-load-377.AC3.3 (disconnect cancellation — code review only):** AC3.3 is verified by code review, not E2E test. NiceGUI's `on_disconnect` callback is triggered by WebSocket closure, which Playwright cannot reliably simulate mid-background-task. The implementation is verified structurally: Task 1 step 5 wires `client.on_disconnect(lambda: task.cancel())`, Task 2 adds `client._deleted` guards at yield points. Code reviewer should verify both are present.

**E2E test conventions:**
- Use `page.get_by_test_id()` for all locators
- Use `await locator.scroll_into_view_if_needed()` before visibility assertions
- Mark with `@pytest.mark.e2e`
- Follow existing E2E fixture patterns (seeded data, authenticated user)

**Verification:**
Run: `uv run grimoire e2e run -k test_deferred_load`
Expected: All tests pass

**Commit:** `test(e2e): deferred page load skeleton and content hydration`

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->
