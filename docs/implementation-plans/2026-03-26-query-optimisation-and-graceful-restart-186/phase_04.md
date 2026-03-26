# Query Optimisation and Graceful Restart — Phase 4

**Goal:** Provide a holding page during server restart that auto-redirects users back to their workspace once the server is healthy.

**Architecture:** A NiceGUI `@ui.page("/restarting")` page (bypassing `page_route` auth, like `/banned`) shows a status message and runs inline JS that polls `/healthz` every 2 seconds. On HTTP 200, it waits a random 1–5 second jitter to prevent thundering herd, then redirects to the `return` URL parameter (defaulting to `/`).

**Tech Stack:** NiceGUI `@ui.page`, inline JavaScript, `fetch()` API

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-03-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### query-optimisation-and-graceful-restart-186.AC3: Restarting page
- **query-optimisation-and-graceful-restart-186.AC3.1 Success:** `/restarting` polls `/healthz`, redirects to return URL on 200
- **query-optimisation-and-graceful-restart-186.AC3.2 Success:** Redirect includes 1–5s random jitter to prevent thundering herd
- **query-optimisation-and-graceful-restart-186.AC3.3 Failure:** Missing `return` param redirects to `/` (home)

---

## Implementation Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `/restarting` page

**Verifies:** query-optimisation-and-graceful-restart-186.AC3.1, query-optimisation-and-graceful-restart-186.AC3.2, query-optimisation-and-graceful-restart-186.AC3.3

**Files:**
- Create: `src/promptgrimoire/pages/restarting.py`
- Modify: `src/promptgrimoire/pages/__init__.py` (add import and `_PAGES` entry)

**Implementation:**

Create `src/promptgrimoire/pages/restarting.py` following the `/banned` page pattern at `pages/banned.py`:

```python
"""Holding page during server restart.

Polls ``/healthz`` every 2 seconds. On HTTP 200, waits a random 1–5 second
jitter (thundering herd prevention) then redirects to the ``return`` query
parameter, defaulting to ``/``.

Uses ``@ui.page`` directly (not ``page_route``) so it is accessible
regardless of authentication state — identical pattern to ``/banned``.
"""

from __future__ import annotations

from nicegui import ui


@ui.page("/restarting")
async def restarting_page() -> None:
    """Display server-updating message with auto-redirect polling."""
    return_url = ui.context.client.request.query_params.get("return", "/")

    with ui.column().classes("absolute-center items-center"):
        ui.icon("update", size="xl").classes("text-blue-500")
        ui.label("Server updating, please wait...").classes(
            "text-2xl font-bold mt-4"
        ).props('data-testid="restarting-message"')
        status = ui.label("Waiting for server...").classes(
            "text-lg text-grey-7 mt-2"
        ).props('data-testid="restarting-status"')

    # Inline JS: poll /healthz, jitter redirect
    ui.add_body_html(f"""<script>
    (function() {{
        const returnUrl = {_js_string(return_url)};
        const pollInterval = 2000;

        async function pollHealthz() {{
            try {{
                const resp = await fetch("/healthz", {{method: "HEAD"}});
                if (resp.ok) {{
                    const jitter = 1000 + Math.random() * 4000;
                    const el = document.querySelector('[data-testid="restarting-status"]');
                    if (el) el.textContent = "Server ready, redirecting...";
                    setTimeout(function() {{
                        window.location.href = returnUrl;
                    }}, jitter);
                    return;
                }}
            }} catch (e) {{
                // Server not ready yet — expected during restart
            }}
            setTimeout(pollHealthz, pollInterval);
        }}

        // Start polling after a brief initial delay (server just went down)
        setTimeout(pollHealthz, pollInterval);
    }})();
    </script>""")
```

Add a helper for safe JS string escaping:

```python
def _js_string(value: str) -> str:
    """Escape a Python string for safe embedding in a JS string literal."""
    import json
    return json.dumps(value)
```

**Register in `pages/__init__.py`:**
Add `from promptgrimoire.pages import restarting` to the import block and `restarting` to the `_PAGES` tuple.

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors

Run: `uv run run.py` then visit `http://localhost:8080/restarting?return=/`
Expected: Page shows message, polls healthz, redirects to `/` within 2-7 seconds

**Commit:** `feat: add /restarting page with healthz polling and jitter redirect (#355)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: E2E test for `/restarting` page

**Verifies:** query-optimisation-and-graceful-restart-186.AC3.1, query-optimisation-and-graceful-restart-186.AC3.2, query-optimisation-and-graceful-restart-186.AC3.3

**Files:**
- Create: `tests/e2e/test_restarting_page.py`

**Testing:**

Tests must verify each AC listed above:

- **AC3.1:** Navigate to `/restarting?return=/`. The page should show the "Server updating" message (verify via `data-testid="restarting-message"`). Since `/healthz` is already responding (dev server is up), the page should redirect to `/` within a reasonable timeout. Use `page.wait_for_url("**/", timeout=10000)` to verify redirect.

- **AC3.2:** The redirect includes jitter. Difficult to test exact timing, but verify the redirect doesn't happen instantly — wait for at least 1 second of polling before expecting the redirect. The jitter is 1-5s, so the full cycle is ~3-7s (2s poll + 1-5s jitter).

- **AC3.3:** Navigate to `/restarting` with NO query params. Verify redirect goes to `/` (home page).

Follow E2E test patterns: `data-testid` locators, `page.get_by_test_id()`.

Test file: `tests/e2e/test_restarting_page.py`

**Verification:**
Run: `uv run grimoire e2e run -k test_restarting`
Expected: All tests pass

**Commit:** `test: add E2E tests for /restarting page (#355)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Complexipy Check

After completing this phase, run:
```bash
uv run complexipy src/promptgrimoire/pages/restarting.py --max-complexity-allowed 15
```

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Navigate to `http://localhost:8080/restarting?return=/` in browser
3. [ ] Verify: "Server updating, please wait..." message is visible
4. [ ] Verify: page redirects to `/` within ~3-7 seconds (2s poll + 1-5s jitter)
5. [ ] Navigate to `http://localhost:8080/restarting` (no return param)
6. [ ] Verify: redirects to `/` (home) after polling

## Evidence Required
- [ ] `uv run grimoire e2e run -k test_restarting` output showing green
- [ ] Screenshot of restarting page showing message
- [ ] Verification that redirect occurs with jitter (not instant)
