# CSS Custom Highlight API — Phase 1: Browser Feature Gate

**Goal:** Block unsupported browsers at login before any annotation code runs.

**Architecture:** Inject client-side JavaScript feature detection (`'highlights' in CSS`) into the login page. Unsupported browsers see an "upgrade your browser" message and cannot proceed. Supported browsers pass through unchanged.

**Tech Stack:** NiceGUI `ui.add_body_html()` for JS injection, CSS Custom Highlight API feature detection.

**Scope:** Phase 1 of 6 from original design (phases 1-6).

**Codebase verified:** 2026-02-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### css-highlight-api.AC4: Browser feature gate
- **css-highlight-api.AC4.1 Success:** Browser with `CSS.highlights` support proceeds to the annotation page normally
- **css-highlight-api.AC4.2 Failure:** Browser without `CSS.highlights` support sees an "upgrade your browser" message and cannot access the annotation page

---

<!-- START_TASK_1 -->
### Task 1: Add browser feature gate to login page

**Verifies:** css-highlight-api.AC4.1, css-highlight-api.AC4.2

**Files:**
- Modify: `src/promptgrimoire/pages/auth.py:326-346` (login_page function)

**Implementation:**

Add a `<script>` block via `ui.add_body_html()` at the top of `login_page()` (after the redirect check for already-authenticated users, before any login UI renders). The script:

1. Checks `'highlights' in CSS`
2. If unsupported: creates a full-page overlay `<div>` with the upgrade message, covering the login UI
3. If supported: does nothing (login UI renders normally)

The overlay approach means the login page HTML renders server-side as normal, then the JS immediately covers it on unsupported browsers. This avoids modifying the NiceGUI component tree from JS (which would fight the framework). The flash is sub-100ms and only affects unsupported browsers.

The message text: "Your browser does not support features required by PromptGrimoire. Please upgrade to Chrome 105+, Firefox 140+, Safari 17.2+, or Edge 105+." with a "Go Home" button linking to `/`.

The JS and overlay CSS should be a Python string constant `_BROWSER_GATE_JS` defined near the top of auth.py (following the existing pattern of JS-in-Python string constants in annotation.py).

**Testing:**

This is an infrastructure gate — the primary verification is operational (E2E). Unit testing JS feature detection is not meaningful without a browser.

Tests must verify each AC listed above:
- css-highlight-api.AC4.1: E2E test navigating to `/login` on a supported browser (Playwright's Chromium) — login UI should be visible, no upgrade message shown
- css-highlight-api.AC4.2: E2E test that navigates to `/login`, then uses `page.evaluate()` to delete `CSS.highlights` (`delete CSS.highlights`) and re-invoke the gate check function. Verify the upgrade overlay becomes visible and covers the login UI. This tests the actual gate UI rendering without requiring a genuinely unsupported browser.

Test file: `tests/e2e/test_browser_gate.py`

**Verification:**
Run: `uv run pytest tests/e2e/test_browser_gate.py -v`
Expected: All tests pass

**Commit:** `feat: add browser feature gate for CSS Custom Highlight API on login page`
<!-- END_TASK_1 -->
