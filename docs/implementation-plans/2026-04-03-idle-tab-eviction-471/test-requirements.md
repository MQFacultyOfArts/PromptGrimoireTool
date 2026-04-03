# Test Requirements: Idle Tab Eviction (#471)

Maps each acceptance criterion to an automated test or documented human verification.

**Conventions:**
- Test type abbreviations: **unit** (pytest xdist), **js** (vitest + happy-dom), **e2e** (Playwright), **integration** (pytest xdist)
- E2E tests in this feature are marked `@pytest.mark.noci` + `@pytest.mark.slow` and require `IDLE__TIMEOUT_SECONDS=5 IDLE__WARNING_SECONDS=2` env vars before server start
- AC6 is DROPPED (see design doc)

---

## AC1: Server reclaims resources from idle clients

| Criterion | Test Type | Test File | Notes |
|-----------|-----------|-----------|-------|
| AC1.1 After 30 min idle, NiceGUI client disconnected and UI tree freed | js | `tests/js/idle-tracker.test.js` :: TestIdleTrackerWallClock | Verifies `window.location.assign("/paused?return=...")` called after timeout elapsed. Wall-clock `Date.now()` via `vi.setSystemTime()`. |
| AC1.1 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestIdleTimeout | With 5s timeout, waits for navigation to `/paused`. Condition-based wait (`wait_for_url`), no fixed sleep. |
| AC1.2 Idle eviction applies to all `page_route` pages | unit | `tests/unit/test_idle_injection.py` | Verifies `ui.add_head_html` called with idle tracker script when `IDLE__ENABLED=true`. Since all authenticated pages use `page_route`, injection coverage is universal. |
| AC1.3 CRDT subscriptions and presence slots released on eviction | -- | **Existing coverage** | Verified by existing `on_delete` lifecycle tests. Idle eviction triggers the standard NiceGUI disconnect -> `reconnect_timeout` -> `client.delete()` -> `on_delete` path. No new tests needed. |
| AC1.4 Interaction at minute 29 resets timer completely | js | `tests/js/idle-tracker.test.js` :: TestIdleTrackerTimerReset | Dispatches `click`/`keypress`/`scroll` events, verifies `lastInteractionTime` resets. |
| AC1.4 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestWarningModal | Clicks during warning window, verifies modal dismissed and timer resets (modal reappears after full new cycle). |
| AC1.5 Wall-clock time, not accumulated setTimeout | js | `tests/js/idle-tracker.test.js` :: TestIdleTrackerWallClock | Uses `vi.useFakeTimers()` + `vi.setSystemTime()` to advance `Date.now()` independently of timer intervals. |

---

## AC2: Students get a warning before eviction

| Criterion | Test Type | Test File | Notes |
|-----------|-----------|-----------|-------|
| AC2.1 Warning modal appears 60s before eviction with live countdown | js | `tests/js/idle-tracker.test.js` :: TestWarningModal | Advances time to `timeout - warning` threshold, verifies modal DOM element with `data-testid="idle-warning-modal"` appears with countdown. |
| AC2.1 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestWarningModal | `get_by_test_id("idle-warning-modal").wait_for(state="visible")`. |
| AC2.2 "Stay Active" button dismisses modal and resets timer | js | `tests/js/idle-tracker.test.js` :: TestWarningModal | Dispatches click on Stay Active button, verifies modal removed from DOM and timer reset. |
| AC2.2 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestWarningModal | Clicks `[data-testid="idle-stay-active-btn"]`, asserts modal disappears, waits for it to reappear (proves reset). |
| AC2.3 Any click/keypress/scroll during warning dismisses modal | js | `tests/js/idle-tracker.test.js` :: TestWarningModal | Dispatches `click` event on `document` while modal shown, verifies dismissal and timer reset. |
| AC2.3 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestWarningModal | Clicks page body during warning window, asserts modal dismissed. |
| AC2.4 visibilitychange in warning window shows modal immediately | js | `tests/js/idle-tracker.test.js` :: TestVisibilityChange | Advances time into warning window, dispatches `visibilitychange` with `hidden=false`, verifies modal appears with correct remaining seconds. |
| AC2.4 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestVisibilityChange | **Approved `page.evaluate()` exception** for simulating `visibilitychange`. |
| AC2.5 visibilitychange past timeout navigates immediately | js | `tests/js/idle-tracker.test.js` :: TestVisibilityChange | Advances time past timeout, dispatches `visibilitychange` with `hidden=false`, verifies `window.location.assign` called without modal. |
| AC2.5 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestVisibilityChange | **Approved `page.evaluate()` exception.** Simulates tab hide/refocus after timeout, asserts navigation to `/paused`. |
| AC2.6 visibilitychange below threshold resets timer (no modal) | js | `tests/js/idle-tracker.test.js` :: TestVisibilityChange | Advances time below warning threshold, dispatches `visibilitychange` with `hidden=false`, verifies no modal and timer reset. |
| AC2.6 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestVisibilityChange | **Approved `page.evaluate()` exception.** Immediate hide/refocus, asserts no modal, then waits for modal to eventually appear (proves reset, not freeze). |

---

## AC3: Evicted students re-enter with priority

| Criterion | Test Type | Test File | Notes |
|-----------|-----------|-----------|-------|
| AC3.1 Evicted user sees Resume button pointing to original page | unit | `tests/unit/test_paused_page.py` :: TestPausedPageReturnUrl | `GET /paused?return=/annotation/some-uuid` -- Resume link href is `/annotation/some-uuid`. |
| AC3.1 (E2E confirmation) | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestResumeFlow | After eviction, asserts Resume button visible and href matches original path. |
| AC3.2 Resume with gate open returns to original page | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestResumeFlow | Clicks Resume after eviction, asserts navigation back to original page. |
| AC3.3 Resume with gate at capacity places user at front of queue | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestAdmissionGatePriority | Uses `/api/dev/admission?cap=0` to close gate, clicks Resume, asserts redirect to `/queue` at position 1 (front via `appendleft`). |
| AC3.4 Open-redirect guard: `https://evil.com` defaults to `/` | unit | `tests/unit/test_paused_page.py` :: TestPausedPageOpenRedirectGuard | Tests `https://evil.com`, `//evil.com`, `javascript:alert(1)` -- all default Resume href to `/`. |
| AC3.5 No `return` param defaults Resume to `/` | unit | `tests/unit/test_paused_page.py` :: TestPausedPageReturnUrl | `GET /paused` (no query param) -- Resume link href is `/`. |
| AC3.6 `/paused` creates no NiceGUI client | unit | `tests/unit/test_paused_page.py` :: TestPausedPageStructure | Starlette `TestClient` request returns 200 `text/html` with no WebSocket upgrade. Raw handler test -- NiceGUI not involved. |

---

## AC4: CRDT state is preserved

| Criterion | Test Type | Test File | Notes |
|-----------|-----------|-----------|-------|
| AC4.1 After eviction and resume, annotations intact | e2e | `tests/e2e/test_idle_tab_eviction.py` :: TestResumeFlow | Creates annotation, waits for CRDT save, waits for eviction, resumes, asserts annotation still present. |
| AC4.2 Mid-edit unsaved text lost, committed CRDT preserved | -- | **Acknowledged, not tested** | This is expected behaviour per the design doc. Unsaved input field text is inherently lost on navigation. Testing would verify browser behaviour, not application logic. No test needed. |

---

## AC5: Configurable via pydantic-settings

| Criterion | Test Type | Test File | Notes |
|-----------|-----------|-----------|-------|
| AC5.1 `IDLE__TIMEOUT_SECONDS=900` sets 15-min timeout | unit | `tests/unit/test_idle_config.py` | `monkeypatch.setenv("IDLE__TIMEOUT_SECONDS", "900")`, asserts `Settings(_env_file=None).idle.timeout_seconds == 900`. |
| AC5.2 `IDLE__WARNING_SECONDS=120` sets 2-min warning | unit | `tests/unit/test_idle_config.py` | `monkeypatch.setenv("IDLE__WARNING_SECONDS", "120")`, asserts `Settings(_env_file=None).idle.warning_seconds == 120`. |
| AC5.3 `IDLE__ENABLED=false` disables eviction | unit | `tests/unit/test_idle_config.py` | `monkeypatch.setenv("IDLE__ENABLED", "false")`, asserts `Settings(_env_file=None).idle.enabled is False`. |
| AC5.3 (injection disabled) | unit | `tests/unit/test_idle_injection.py` | With `IDLE__ENABLED=false`, verifies `ui.add_head_html` NOT called with idle tracker content. |
| AC5.3 (JS disabled) | js | `tests/js/idle-tracker.test.js` :: TestIdleTrackerConfig | When `window.__idleConfig` absent or `enabled: false`, no event listeners attached, no polling started. |
| AC5.4 Defaults: 1800s timeout, 60s warning, enabled=true | unit | `tests/unit/test_idle_config.py` | Clears `IDLE__*` env vars, asserts `IdleConfig()` defaults. |

---

## AC6: Login page element reduction -- DROPPED

Not implemented. Replaced by AC7. No tests.

---

## AC7: Pre-auth landing page

| Criterion | Test Type | Test File | Notes |
|-----------|-----------|-----------|-------|
| AC7.1 `GET /welcome` returns static HTML with Login button linking to `/login?return=/` | unit | `tests/unit/test_welcome_page.py` :: TestWelcomePageStructure + TestWelcomePageLoginLink | Returns 200 `text/html`, contains "PromptGrimoire", Login link href is `/login?return=/`. |
| AC7.2 `/welcome` creates no NiceGUI client | unit | `tests/unit/test_welcome_page.py` :: TestWelcomePageStructure | Starlette `TestClient` request -- raw handler, no WebSocket. |
| AC7.3 Login on `/welcome` navigates to `/login?return=/`, auth returns to `/` | unit | `tests/unit/test_welcome_page.py` :: TestWelcomePageLoginLink | Verifies link includes `return=/` query parameter. Full auth round-trip relies on existing `/login?return=` test coverage. |
| AC7.4 Same visual style as `/paused` and `/queue` | -- | **Human verification** | Visual style consistency across raw Starlette pages cannot be meaningfully automated. **Verification approach:** During UAT, open `/welcome`, `/paused`, and `/queue` side by side and confirm matching font, layout, card dimensions, and colour scheme. |

---

## Human Verification Summary

| Criterion | Justification | Verification Approach |
|-----------|---------------|----------------------|
| AC1.3 | Covered by existing `on_delete` tests | Review existing test coverage during code review; no new test needed unless `on_delete` handlers change. |
| AC4.2 | Expected browser behaviour, not application logic | Acknowledged in design doc. No verification needed. |
| AC7.4 | Visual style consistency is subjective and layout-dependent | UAT: open `/welcome`, `/paused`, `/queue` side by side in a browser. Confirm matching font family (`system-ui`), background colour (`#f5f5f5`), card width (`max-width: 400px`), and centred layout. |

---

## Test File Summary

| Test File | Type | Lane | Phase | Criteria Covered |
|-----------|------|------|-------|-----------------|
| `tests/unit/test_idle_config.py` | unit | unit (xdist) | 1 | AC5.1, AC5.2, AC5.3, AC5.4 |
| `tests/unit/test_paused_page.py` | unit | unit (xdist) | 2 | AC3.1, AC3.4, AC3.5, AC3.6 |
| `tests/js/idle-tracker.test.js` | js | js (vitest) | 3 | AC1.1, AC1.4, AC1.5, AC2.1-AC2.6, AC5.3 |
| `tests/unit/test_idle_injection.py` | unit | unit (xdist) | 4 | AC1.2, AC5.3 |
| `tests/unit/test_welcome_page.py` | unit | unit (xdist) | 5 | AC7.1, AC7.2, AC7.3 |
| `tests/e2e/test_idle_tab_eviction.py` | e2e | playwright (noci+slow) | 6 | AC1.1, AC1.4, AC2.1-AC2.6, AC3.1-AC3.3, AC4.1 |

---

## Run Commands

```bash
# Phase 1: config tests
uv run grimoire test run tests/unit/test_idle_config.py

# Phase 2: /paused handler tests
uv run grimoire test run tests/unit/test_paused_page.py

# Phase 3: JS idle tracker tests
uv run grimoire test js

# Phase 4: injection tests
uv run grimoire test run tests/unit/test_idle_injection.py

# Phase 5: /welcome handler tests
uv run grimoire test run tests/unit/test_welcome_page.py

# Phase 6: E2E tests (requires env vars before server start)
IDLE__TIMEOUT_SECONDS=5 IDLE__WARNING_SECONDS=2 uv run grimoire e2e slow -k test_idle_tab_eviction

# All unit + JS tests together
uv run grimoire test all
```
