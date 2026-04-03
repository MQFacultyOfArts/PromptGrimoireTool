# Idle Tab Eviction Implementation Plan

**Goal:** End-to-end tests covering the full idle -> warning -> eviction -> resume cycle

**Architecture:** Playwright E2E tests with short timeouts (`IDLE__TIMEOUT_SECONDS=5`, `IDLE__WARNING_SECONDS=2`) set as env vars before server start. Uses `authenticated_page` fixture for authenticated access, `page.evaluate()` for visibilitychange simulation, and `/api/dev/admission` endpoint for gate manipulation.

**Tech Stack:** Playwright, pytest (already in use)

**Scope:** 7 phases from original design (phases 1-7, original Phase 5 replaced by pre-auth landing page)

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

### idle-tab-eviction-471.AC1: Server reclaims resources from idle clients
- **idle-tab-eviction-471.AC1.1 Success:** After 30 minutes of no click/keypress/scroll, the NiceGUI client is disconnected and its UI tree is freed from server memory
- **idle-tab-eviction-471.AC1.2 Success:** Idle eviction applies to all `page_route`-decorated pages (annotation, navigator, courses, roleplay)
- **idle-tab-eviction-471.AC1.3 Success:** CRDT subscriptions and remote presence slots are released on eviction (existing `on_delete` lifecycle) — **NOTE:** Verified by existing `on_delete` test coverage, not new tests in this phase. Idle eviction triggers the standard NiceGUI disconnect → `reconnect_timeout` → `client.delete()` → `on_delete` lifecycle. No new test needed unless `on_delete` handlers change.
- **idle-tab-eviction-471.AC1.4 Edge:** A click/keypress/scroll at minute 29 resets the 30-minute timer completely
- **idle-tab-eviction-471.AC1.5 Edge:** Idle timer uses wall-clock time (`Date.now()`), not accumulated `setTimeout` intervals — Chrome tab throttling does not delay eviction beyond the configured timeout

### idle-tab-eviction-471.AC2: Students get a warning before eviction
- **idle-tab-eviction-471.AC2.1 Success:** Warning modal appears 60 seconds before eviction with a live countdown
- **idle-tab-eviction-471.AC2.2 Success:** Clicking "Stay Active" on the modal dismisses it and resets the idle timer
- **idle-tab-eviction-471.AC2.3 Success:** Any click/keypress/scroll during the warning window dismisses the modal and resets the timer
- **idle-tab-eviction-471.AC2.4 Success:** On `visibilitychange` (tab refocus), if in warning window, modal appears immediately with correct remaining time
- **idle-tab-eviction-471.AC2.5 Success:** On `visibilitychange`, if past timeout, navigation to `/paused` occurs immediately without showing the modal
- **idle-tab-eviction-471.AC2.6 Edge:** On `visibilitychange`, if below warning threshold, focus event resets the timer (no modal shown)

### idle-tab-eviction-471.AC3: Evicted students re-enter with priority
- **idle-tab-eviction-471.AC3.1 Success:** Evicted user navigates to `/paused?return={original_path}` and sees Resume button pointing to the original page
- **idle-tab-eviction-471.AC3.2 Success:** Clicking Resume with admission gate open returns user directly to their original page
- **idle-tab-eviction-471.AC3.3 Success:** Clicking Resume with admission gate at capacity places user at front of queue (`appendleft`), not the back

### idle-tab-eviction-471.AC4: CRDT state is preserved
- **idle-tab-eviction-471.AC4.1 Success:** After eviction and resume, all previously saved annotations are intact (CRDT state persisted via existing `on_delete` handler)

---

<!-- START_TASK_1 -->
### Task 1: E2E test file setup and idle timeout test

**Verifies:** idle-tab-eviction-471.AC1.1, idle-tab-eviction-471.AC1.5

**Files:**
- Create: `tests/e2e/test_idle_tab_eviction.py`

**Implementation:**

Create E2E test file with markers:
```python
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.noci,
    pytest.mark.slow,
]
```

The test file requires `IDLE__TIMEOUT_SECONDS=5` and `IDLE__WARNING_SECONDS=2` to be set as environment variables **before the E2E server starts**. Since `get_settings()` is called at server startup (before tests run), `monkeypatch.setenv` is too late. These tests must be run with env vars on the command line:

```bash
IDLE__TIMEOUT_SECONDS=5 IDLE__WARNING_SECONDS=2 uv run grimoire e2e slow -k test_idle_tab_eviction
```

Add a skip guard at the top of the test file that skips gracefully when the short values aren't set:
```python
pytestmark.append(
    pytest.mark.skipif(
        os.environ.get("IDLE__TIMEOUT_SECONDS", "1800") != "5",
        reason="Requires IDLE__TIMEOUT_SECONDS=5 (set via env var before server start)",
    )
)
```

This matches how the project handles `DATABASE__URL`-dependent tests.

**Nightly workflow update required:** The nightly `e2e slow` workflow (`nightly-e2e-slow.yml`) must be updated to set `IDLE__TIMEOUT_SECONDS=5 IDLE__WARNING_SECONDS=2` in the environment. Without this, Phase 6 tests will be silently skipped in every nightly run. Add this as a task during Phase 6 implementation.

**Testing:**

**TestIdleTimeout:**
- idle-tab-eviction-471.AC1.1: Authenticate, navigate to a page_route page (e.g., `/`). Use `page.wait_for_url("**/paused**", timeout=10000)` — condition-based wait, no fixed sleep. Assert URL contains `/paused?return=...`. Assert page contains "paused" text and a Resume button.
- idle-tab-eviction-471.AC1.5: Same test — the 5-second timeout proves wall-clock works (accumulated timer would take longer in hidden tabs).

Use `authenticated_page` fixture. After authentication, navigate to the target page and wait without interaction. **All waits must be condition-based** (`wait_for_url`, `wait_for_selector`, `expect(...).to_be_visible()`) — never `time.sleep()` or fixed delays.

**Verification:**

Run: `uv run grimoire e2e slow -k test_idle_tab_eviction`
Expected: Test passes within 15 seconds

**Commit:** `test(idle): add E2E test for idle timeout eviction`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Warning modal E2E tests

**Verifies:** idle-tab-eviction-471.AC2.1, idle-tab-eviction-471.AC2.2, idle-tab-eviction-471.AC2.3, idle-tab-eviction-471.AC1.4

**Files:**
- Modify: `tests/e2e/test_idle_tab_eviction.py`

**Testing:**

**TestWarningModal:**
- idle-tab-eviction-471.AC2.1: Navigate to authenticated page. Use `page.get_by_test_id("idle-warning-modal").wait_for(state="visible", timeout=10000)` — condition-based wait for modal appearance. Assert modal contains countdown text.
- idle-tab-eviction-471.AC2.2: Wait for modal to appear (condition-based). Click `[data-testid="idle-stay-active-btn"]`. Assert modal disappears via `expect(modal).not_to_be_visible()`. Wait for modal to reappear again (condition-based). Assert URL is NOT `/paused` yet.
- idle-tab-eviction-471.AC2.3: Wait for modal to appear (condition-based). Click anywhere on the page body. Assert modal disappears and timer resets.
- idle-tab-eviction-471.AC1.4: Navigate to page. Wait for modal to appear (condition-based). Click the page (interaction during warning window). Assert modal dismissed. Wait for modal to reappear (condition-based — proves timer reset completely). Assert URL is still not `/paused`.

**Verification:**

Run: `uv run grimoire e2e slow -k TestWarningModal`
Expected: All tests pass

**Commit:** `test(idle): add E2E tests for warning modal interaction`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: visibilitychange E2E tests

**Verifies:** idle-tab-eviction-471.AC2.4, idle-tab-eviction-471.AC2.5, idle-tab-eviction-471.AC2.6

**Files:**
- Modify: `tests/e2e/test_idle_tab_eviction.py`

**Testing:**

**NOTE: Project-level exception granted for `page.evaluate()` in this task.** The project's "NEVER inject JavaScript" E2E rule has an explicit exception for `visibilitychange` simulation because Playwright has no native API for tab visibility. This exception was approved by Brian on 2026-04-03 during implementation planning.

**TestVisibilityChange:**

Simulate tab hide/show via `page.evaluate()`:
```python
# Simulate tab hidden
page.evaluate("""() => {
    Object.defineProperty(document, 'hidden', {value: true, configurable: true});
    document.dispatchEvent(new Event('visibilitychange'));
}""")

# Simulate tab visible (refocus)
page.evaluate("""() => {
    Object.defineProperty(document, 'hidden', {value: false, configurable: true});
    document.dispatchEvent(new Event('visibilitychange'));
}""")
```

- idle-tab-eviction-471.AC2.5: Navigate to page. Use `page.wait_for_url("**/paused**", timeout=10000)` to wait for eviction (condition-based). Then navigate back to the original page. Simulate tab hide, then simulate tab refocus. Use `page.wait_for_url("**/paused**")` — should navigate immediately.
- idle-tab-eviction-471.AC2.4: Navigate to page. Use `page.get_by_test_id("idle-warning-modal").wait_for(state="visible", timeout=10000)` to wait for modal (condition-based). Dismiss via Stay Active. Simulate tab hide. Wait for warning modal to reappear (condition-based). Simulate tab refocus. Assert modal is still visible with countdown.
- idle-tab-eviction-471.AC2.6: Navigate to page. Immediately simulate tab hide then refocus (well before warning threshold). Use `expect(page.get_by_test_id("idle-warning-modal")).not_to_be_visible()`. Then wait for modal to appear (condition-based — proves timer was reset by refocus, not frozen).

**Verification:**

Run: `uv run grimoire e2e slow -k TestVisibilityChange`
Expected: All tests pass

**Commit:** `test(idle): add E2E tests for visibilitychange tab refocus`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Resume and admission gate priority E2E tests

**Verifies:** idle-tab-eviction-471.AC3.1, idle-tab-eviction-471.AC3.2, idle-tab-eviction-471.AC3.3, idle-tab-eviction-471.AC4.1

**Note on AC4.2:** Unsaved text in input fields is lost on eviction — this is acknowledged, expected behaviour per the design doc, not a bug. No test needed.

**Files:**
- Modify: `tests/e2e/test_idle_tab_eviction.py`

**Testing:**

**TestResumeFlow:**
- idle-tab-eviction-471.AC3.1 + AC3.2: Navigate to authenticated page (e.g., `/`). Wait for eviction to `/paused`. Assert Resume button is visible and points to original page. Click Resume. Assert navigation back to original page (gate open, direct re-entry).
- idle-tab-eviction-471.AC4.1: If testing with annotation workspace: create a workspace, add an annotation, wait for CRDT save. Wait for eviction. Resume. Assert annotation is still present.

**TestAdmissionGatePriority:**
- idle-tab-eviction-471.AC3.3: Navigate to authenticated page. Wait for eviction. Use dev endpoint to set admission gate cap to 0 (`/api/dev/admission?cap=0`). Click Resume on `/paused`. Assert redirect to `/queue` (gate at capacity). Verify the user is at position 1 in queue (front, not back). Reset gate cap (`/api/dev/admission?cap=100`). Assert eventual redirect back to original page.

**Verification:**

Run: `uv run grimoire e2e slow -k TestResumeFlow`
Expected: All tests pass

**Commit:** `test(idle): add E2E tests for resume flow and admission gate priority`
<!-- END_TASK_4 -->
