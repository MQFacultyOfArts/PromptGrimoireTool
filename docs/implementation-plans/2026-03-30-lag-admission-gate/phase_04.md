# Lag-Based Admission Gate Implementation Plan

**Goal:** Raw Starlette queue page and JSON status endpoint — zero NiceGUI overhead for queued users.

**Architecture:** Two new Starlette routes registered via `app.routes.insert(0, ...)`: `/queue` returns HTMLResponse with inline vanilla JS polling, `/api/queue/status` returns JSONResponse with queue position/admission status. Both validate via queue token (UUID4), no Stytch round-trips.

**Tech Stack:** Python 3.14, Starlette (HTMLResponse, JSONResponse, Route), vanilla JS

**Scope:** 5 phases from original design (phase 4 of 5)

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

This phase implements and tests:

### lag-admission-gate.AC4: Queue page is lightweight and functional
- **lag-admission-gate.AC4.1 Success:** Queue page shows user's position and total queue size
- **lag-admission-gate.AC4.2 Success:** Queue page polls `/api/queue/status?t=<token>` every 5s via vanilla JS and redirects to original page on admission
- **lag-admission-gate.AC4.3 Success:** `/api/queue/status?t=<token>` returns `{position, total, admitted, expired}` JSON
- **lag-admission-gate.AC4.4 Edge:** `/api/queue/status` with invalid or missing token returns `{admitted: false, expired: true}` — queue page shows "rejoin" link
- **lag-admission-gate.AC4.5 Success:** Queue page is a raw Starlette HTML response — zero NiceGUI client overhead
- **lag-admission-gate.AC4.6 Edge:** Queue page shows "your place has expired" with rejoin link when `expired: true`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Queue status API endpoint

**Verifies:** lag-admission-gate.AC4.3, lag-admission-gate.AC4.4

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (add Starlette route, near existing route registrations around line 292-308)
- Create: `tests/unit/test_queue_status_api.py`

**Implementation:**

Add a `queue_status_handler` async function and register it as a Starlette route. Follow the existing pattern from `healthz` and `kick_user_handler`.

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

async def queue_status_handler(request: Request) -> JSONResponse:
    from promptgrimoire.admission import get_admission_state

    token = request.query_params.get("t", "")
    state = get_admission_state()
    status = state.get_queue_status(token)
    return JSONResponse(status)
```

Register after existing routes:
```python
app.routes.insert(0, Route("/api/queue/status", queue_status_handler, methods=["GET"]))
```

The `get_queue_status(token)` method (from Phase 1) returns the dict directly:
- Valid token, user in queue: `{"position": N, "total": M, "admitted": false, "expired": false}`
- Valid token, user admitted: `{"position": 0, "total": M, "admitted": true, "expired": false}`
- Invalid/missing/expired token: `{"position": 0, "total": 0, "admitted": false, "expired": true}`

**Testing:**

Test file: `tests/unit/test_queue_status_api.py`

Tests mock `get_admission_state()` and call the handler directly with a mock Request:

- lag-admission-gate.AC4.3: Mock state where token maps to queued user at position 2 of 5. Verify JSON response has `position=2, total=5, admitted=false, expired=false`.
- lag-admission-gate.AC4.3 (admitted): Mock state where token maps to admitted user. Verify `admitted=true`.
- lag-admission-gate.AC4.4: Call with `t=invalid-token`. Verify `admitted=false, expired=true`.
- lag-admission-gate.AC4.4: Call with no `t` parameter. Verify `admitted=false, expired=true`.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_queue_status_api.py`
Expected: All tests pass

**Commit:** `feat: add /api/queue/status Starlette endpoint`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Queue page (raw Starlette HTML)

**Verifies:** lag-admission-gate.AC4.1, lag-admission-gate.AC4.2, lag-admission-gate.AC4.5, lag-admission-gate.AC4.6

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (add Starlette route)
- Create: `tests/unit/test_queue_page.py`

**Implementation:**

Add a `queue_page_handler` async function returning `HTMLResponse` with inline vanilla JS. Follow the JS polling pattern from `pages/restarting.py` (IIFE with setTimeout + fetch).

The HTML page must:
- Read `t` (token) and `return` (original URL) from query parameters
- Embed them safely in JS via `json.dumps().replace("</", "<\\/")` (XSS prevention — same pattern as restarting.py)
- Show initial "Loading queue position..." message
- Poll `/api/queue/status?t=<token>` every 5s
- On `admitted: true` → `window.location.href = returnUrl`
- On `expired: true` → show "Your place in the queue has expired" with a link to `returnUrl` (which re-triggers the gate)
- Update position display on each poll: "You are position N of M in the queue"
- Include basic semantic HTML: `<main>`, `<h1>`, `<p>`, proper `<meta charset>` and viewport

The page should also include:
- `<noscript>` fallback: "JavaScript is required for the queue page"
- Minimal inline CSS for readability (centered content, reasonable font size)
- No external CSS/JS dependencies

```python
from starlette.responses import HTMLResponse

async def queue_page_handler(request: Request) -> HTMLResponse:
    import json

    token = request.query_params.get("t", "")
    raw_return = request.query_params.get("return", "/")

    # Open-redirect guard: return URL must be a relative path starting with /
    # Rejects javascript:, data:, protocol-relative (//), and absolute URLs
    return_url = raw_return if raw_return.startswith("/") and not raw_return.startswith("//") else "/"

    # Safe JS embedding (prevent XSS via </script> injection)
    safe_token = json.dumps(token).replace("</", "<\\/")
    safe_return = json.dumps(return_url).replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Queue - PromptGrimoire</title>
    <style>
        body {{ font-family: system-ui, sans-serif; display: flex;
               justify-content: center; align-items: center;
               min-height: 100vh; margin: 0; background: #f5f5f5; }}
        main {{ text-align: center; max-width: 400px; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
        #position {{ font-size: 1.2rem; margin: 1rem 0; }}
        #expired {{ display: none; }}
        a {{ color: #1976d2; }}
    </style>
</head>
<body>
    <main>
        <h1>Server is busy</h1>
        <p id="position">Loading queue position...</p>
        <p>Users are admitted in batches. This page updates automatically.</p>
        <div id="expired">
            <p>Your place in the queue has expired.</p>
            <p><a id="rejoin" href="/">Rejoin the queue</a></p>
        </div>
        <noscript><p>JavaScript is required for the queue page.</p></noscript>
    </main>
    <script>
    (function() {{
        var token = {safe_token};
        var returnUrl = {safe_return};
        var posEl = document.getElementById("position");
        var expEl = document.getElementById("expired");
        var rejoinEl = document.getElementById("rejoin");
        rejoinEl.href = returnUrl;

        async function poll() {{
            try {{
                var r = await fetch("/api/queue/status?t=" + encodeURIComponent(token));
                if (r.ok) {{
                    var d = await r.json();
                    if (d.admitted) {{
                        window.location.href = returnUrl;
                        return;
                    }}
                    if (d.expired) {{
                        posEl.style.display = "none";
                        expEl.style.display = "block";
                        return;
                    }}
                    posEl.textContent = "You are position " + d.position + " of " + d.total + " in the queue.";
                }}
            }} catch (e) {{ /* server may be restarting */ }}
            setTimeout(poll, 5000);
        }}
        setTimeout(poll, 1000);
    }})();
    </script>
</body>
</html>"""
    return HTMLResponse(html)
```

Register the route:
```python
app.routes.insert(0, Route("/queue", queue_page_handler, methods=["GET"]))
```

**Design divergence note:** The design plan originally specified `src/promptgrimoire/pages/queue.py` as a `@ui.page`. The implementation places the handler in `__init__.py` as a raw Starlette route instead, following the existing pattern for `/healthz`, `/api/admin/kick`, etc. This avoids creating a NiceGUI client per queued user. The design plan has been updated to reflect this change. The restart resilience originally planned for `queue.py` is handled by the JS `catch` block — when the server restarts, fetch errors are silently swallowed and retried; when the server comes back, the next poll returns `expired: true` (fresh state has no tokens), and the page shows the rejoin link.

**Testing:**

Test file: `tests/unit/test_queue_page.py`

- lag-admission-gate.AC4.5: Call handler with mock request. Verify response is HTMLResponse, content-type is text/html, no NiceGUI imports in response.
- lag-admission-gate.AC4.1: Verify HTML contains `id="position"` element.
- lag-admission-gate.AC4.2: Verify HTML contains `fetch("/api/queue/status?t="` polling JS.
- lag-admission-gate.AC4.6: Verify HTML contains `id="expired"` element with rejoin link.
- XSS prevention: Pass `token='</script><script>alert(1)'` and verify it's JSON-escaped in the output HTML.
- Open-redirect guard: Pass `return=javascript:alert(1)`. Verify return_url defaults to `/` in the rendered HTML.
- Open-redirect guard: Pass `return=//evil.com`. Verify return_url defaults to `/`.
- Open-redirect guard: Pass `return=https://evil.com`. Verify return_url defaults to `/`.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_queue_page.py`
Expected: All tests pass

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: add /queue raw Starlette HTML page with vanilla JS polling`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
