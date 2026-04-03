# Idle Tab Eviction Implementation Plan

**Goal:** Client-side idle detection with warning modal and eviction navigation

**Architecture:** A self-contained global-scope JS module (`idle-tracker.js`) that reads config from `window.__idleConfig`, tracks user inactivity via wall-clock `Date.now()` timestamps, shows a warning modal overlay, and navigates to `/paused?return=...` on timeout. Uses adaptive polling interval (`min(10s, warningMs / 2)`). Warning modal is pure DOM (no NiceGUI elements).

**Tech Stack:** Vanilla JavaScript, vitest + happy-dom (already in use)

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

### idle-tab-eviction-471.AC1: Server reclaims resources from idle clients
- **idle-tab-eviction-471.AC1.1 Success:** After 30 minutes of no click/keypress/scroll, the NiceGUI client is disconnected and its UI tree is freed from server memory
- **idle-tab-eviction-471.AC1.4 Edge:** A click/keypress/scroll at minute 29 resets the 30-minute timer completely
- **idle-tab-eviction-471.AC1.5 Edge:** Idle timer uses wall-clock time (`Date.now()`), not accumulated `setTimeout` intervals — Chrome tab throttling does not delay eviction beyond the configured timeout

### idle-tab-eviction-471.AC2: Students get a warning before eviction
- **idle-tab-eviction-471.AC2.1 Success:** Warning modal appears 60 seconds before eviction with a live countdown
- **idle-tab-eviction-471.AC2.2 Success:** Clicking "Stay Active" on the modal dismisses it and resets the idle timer
- **idle-tab-eviction-471.AC2.3 Success:** Any click/keypress/scroll during the warning window dismisses the modal and resets the timer
- **idle-tab-eviction-471.AC2.4 Success:** On `visibilitychange` (tab refocus), if in warning window, modal appears immediately with correct remaining time
- **idle-tab-eviction-471.AC2.5 Success:** On `visibilitychange`, if past timeout, navigation to `/paused` occurs immediately without showing the modal
- **idle-tab-eviction-471.AC2.6 Edge:** On `visibilitychange`, if below warning threshold, focus event resets the timer (no modal shown)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: idle-tracker.js core module

**Verifies:** idle-tab-eviction-471.AC1.1, idle-tab-eviction-471.AC1.4, idle-tab-eviction-471.AC1.5, idle-tab-eviction-471.AC2.5

**Files:**
- Create: `src/promptgrimoire/static/idle-tracker.js`

**Implementation:**

Create a plain global-scope JS file (no ES modules, matching existing `annotation-highlight.js` pattern). The module should:

1. **Initialisation function** (`initIdleTracker()`): Called at load time. Reads `window.__idleConfig` (`{ timeoutMs, warningMs, enabled }`). If not present or `enabled === false`, return immediately without attaching any listeners.

2. **State**: `lastInteractionTime = Date.now()` stored in closure. `warningModalShown = false`.

3. **Event listeners**: Attach `click`, `keypress`, `scroll` listeners on `document` (passive). Each sets `lastInteractionTime = Date.now()` and dismisses warning modal if shown. **Critical: Use named function references** (e.g., `function onInteraction() { ... }`) — NOT anonymous lambdas. `cleanupIdleTracker()` needs to call `removeEventListener` with the same reference to detach them. Store references in closure variables.

4. **Polling loop**: `setInterval` with adaptive interval `Math.min(10000, warningMs / 2)`. On each tick:
   - `elapsed = Date.now() - lastInteractionTime`
   - If `elapsed >= timeoutMs`: navigate to `/paused?return=${encodeURIComponent(window.location.pathname + window.location.search)}`
   - If `elapsed >= timeoutMs - warningMs` and modal not shown: show warning modal with countdown
   - If modal shown: update countdown display

5. **`visibilitychange` handler**: On `document` `visibilitychange` event, if `document.hidden === false`:
   - `elapsed = Date.now() - lastInteractionTime`
   - If `elapsed >= timeoutMs`: navigate immediately (AC2.5)
   - If `elapsed >= timeoutMs - warningMs`: show modal with correct remaining time (AC2.4)
   - Else: reset timer (focus counts as interaction) (AC2.6)

6. **Navigation**: Use `window.location.assign(url)` for eviction navigation.

7. **Do NOT self-invoke.** Define `initIdleTracker()` as a global function but do not call it at script load time. Phase 4's injected `<script>` will call `initIdleTracker()` explicitly after setting `window.__idleConfig`. This allows Vitest tests to re-invoke per test with fresh state.

**Verification:**

Manually test by temporarily adding the script to a page with `window.__idleConfig = {timeoutMs: 10000, warningMs: 3000, enabled: true}`.

**Commit:** `feat(idle): add idle-tracker.js core module`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Warning modal rendering

**Verifies:** idle-tab-eviction-471.AC2.1, idle-tab-eviction-471.AC2.2, idle-tab-eviction-471.AC2.3

**Files:**
- Modify: `src/promptgrimoire/static/idle-tracker.js` (add modal rendering functions)

**Implementation:**

Add to `idle-tracker.js`:

1. **`showWarningModal(remainingSeconds)`**: Creates a fixed-position DOM overlay (`position: fixed; inset: 0; z-index: 99999; background: rgba(0,0,0,0.5)`) with a centred card containing:
   - "Session will pause in N seconds" heading
   - Live countdown updated every 1 second (inner `setInterval`, only while modal visible and tab not hidden)
   - "Stay Active" button that dismisses modal and resets idle timer
   - Set `data-testid="idle-warning-modal"` on the overlay root
   - Set `data-testid="idle-stay-active-btn"` on the Stay Active button

2. **`hideWarningModal()`**: Removes the modal element from DOM, clears the countdown interval, sets `warningModalShown = false`.

3. **Integration with event listeners**: The `click`/`keypress`/`scroll` handlers should call `hideWarningModal()` if modal is shown, then reset the timer.

**Verification:**

After Task 1, set a short timeout config and wait for the warning modal to appear. Click "Stay Active" — modal should dismiss and timer should reset.

**Commit:** `feat(idle): add warning modal to idle-tracker.js`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Vitest tests for idle-tracker.js

**Verifies:** idle-tab-eviction-471.AC1.1, idle-tab-eviction-471.AC1.4, idle-tab-eviction-471.AC1.5, idle-tab-eviction-471.AC2.1, idle-tab-eviction-471.AC2.2, idle-tab-eviction-471.AC2.3, idle-tab-eviction-471.AC2.4, idle-tab-eviction-471.AC2.5, idle-tab-eviction-471.AC2.6

**Files:**
- Create: `tests/js/idle-tracker.test.js`
- Modify: `tests/js/setup.js` (add idle-tracker.js to the evaluated file list)

**Testing:**

Add `idle-tracker.js` to `tests/js/setup.js` file list (alongside existing static JS files) so it's evaluated into global scope before tests.

Test groups:

**TestIdleTrackerConfig:**
- idle-tab-eviction-471.AC5.3: When `window.__idleConfig` is absent or `enabled: false`, no event listeners attached, no polling started
- When config present with `enabled: true`, event listeners are attached

**TestIdleTrackerTimerReset:**
- idle-tab-eviction-471.AC1.4: After `click` event at elapsed time < timeout, `lastInteractionTime` resets (subsequent check shows 0 elapsed)
- Same for `keypress` and `scroll` events

**TestIdleTrackerWallClock:**
- idle-tab-eviction-471.AC1.5: Use `vi.useFakeTimers()` + `vi.setSystemTime()` to advance `Date.now()` by timeout duration. Verify `window.location.assign` called with `/paused?return=...`
- idle-tab-eviction-471.AC1.1: Same test but verify the navigation URL includes the current path

**TestWarningModal:**
- idle-tab-eviction-471.AC2.1: Advance time to `timeout - warning` threshold. Trigger polling tick. Modal element appears in DOM with countdown.
- idle-tab-eviction-471.AC2.2: Show modal, dispatch click on "Stay Active" button. Modal removed from DOM, timer reset.
- idle-tab-eviction-471.AC2.3: Show modal, dispatch `click` event on document. Modal removed, timer reset.

**TestVisibilityChange:**
- idle-tab-eviction-471.AC2.5: Set `document.hidden = false` via `Object.defineProperty`, advance time past timeout, dispatch `visibilitychange`. Verify `window.location.assign` called immediately.
- idle-tab-eviction-471.AC2.4: Advance time into warning window, dispatch `visibilitychange` with `hidden=false`. Verify modal appears with correct remaining seconds.
- idle-tab-eviction-471.AC2.6: Advance time below warning threshold, dispatch `visibilitychange` with `hidden=false`. Verify no modal shown, timer reset.

**Setup/teardown pattern:**
- `beforeEach`: `vi.useFakeTimers()`, set `window.__idleConfig`, clean up any existing modal DOM
- `afterEach`: `vi.useRealTimers()`, `vi.restoreAllMocks()`, delete `window.__idleConfig`

**Init strategy (resolved):** `idle-tracker.js` does NOT auto-invoke. `setup.js` evaluates the file to make `initIdleTracker()` available as a global function. Each test calls `initIdleTracker()` explicitly after setting up `window.__idleConfig` and fake timers. Each `afterEach` must clean up: remove event listeners, clear intervals, remove modal DOM, delete `window.__idleConfig`. Add a `cleanupIdleTracker()` function to `idle-tracker.js` that removes all listeners and clears all state — tests call this in `afterEach`.

**Verification:**

Run: `uv run grimoire test js`
Expected: All idle-tracker tests pass

**Commit:** `test(idle): add vitest tests for idle-tracker.js`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
