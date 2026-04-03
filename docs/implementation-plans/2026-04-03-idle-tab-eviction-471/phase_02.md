# Idle Tab Eviction Implementation Plan

**Goal:** Lightweight Starlette handler for the `/paused` landing page with open-redirect guard

**Architecture:** Raw Starlette handler in `queue_handlers.py` following the existing `/queue` pattern. Returns `HTMLResponse` with inline CSS, vanilla JS Resume button. No NiceGUI client created. Open-redirect guard uses `_SAFE_RETURN_RE` pattern from `auth.py`.

**Tech Stack:** Starlette (already in use)

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

### idle-tab-eviction-471.AC3: Evicted students re-enter with priority
- **idle-tab-eviction-471.AC3.1 Success:** Evicted user navigates to `/paused?return={original_path}` and sees Resume button pointing to the original page
- **idle-tab-eviction-471.AC3.4 Failure:** `/paused?return=https://evil.com` defaults to `/` (open-redirect guard)
- **idle-tab-eviction-471.AC3.5 Failure:** `/paused` with no `return` parameter defaults Resume to `/`
- **idle-tab-eviction-471.AC3.6 Success:** `/paused` page creates no NiceGUI client (raw Starlette handler)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: `/paused` Starlette handler

**Verifies:** idle-tab-eviction-471.AC3.1, idle-tab-eviction-471.AC3.4, idle-tab-eviction-471.AC3.5, idle-tab-eviction-471.AC3.6

**Files:**
- Modify: `src/promptgrimoire/queue_handlers.py` (add `paused_page_handler` and `_build_paused_html`)

**Implementation:**

Add a `_SAFE_RETURN_RE` pattern (same regex as `auth.py:32`: `^/([^/].*)?$`) at module level in `queue_handlers.py`. This avoids a cross-module import from auth to a Starlette handler module.

Add `paused_page_handler(request: Request) -> HTMLResponse`:
- Extract `return` query param, validate against `_SAFE_RETURN_RE`, default to `/`
- Return `HTMLResponse(_build_paused_html(return_url))`

Add `_build_paused_html(return_url: str) -> str`:
- Follow the same inline HTML pattern as `_build_queue_html`
- Centred card layout with "Your session was paused due to inactivity" heading
- Resume button as an `<a>` tag pointing to the validated `return_url`
- Inline CSS matching the queue page's styling (system-ui font, flexbox centred, `#f5f5f5` background, `max-width: 400px` card)
- HTML-escape the `return_url` in the href attribute to prevent XSS

**Verification:**

Run: `uv run python -c "from promptgrimoire.queue_handlers import _build_paused_html; print(_build_paused_html('/annotation/test'))"`
Expected: HTML string containing Resume link pointing to `/annotation/test`

**Commit:** `feat(idle): add /paused Starlette handler with open-redirect guard`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Route registration for `/paused`

**Verifies:** idle-tab-eviction-471.AC3.6

**Files:**
- Modify: `src/promptgrimoire/__init__.py:305-319` (add `/paused` route alongside `/queue`)

**Implementation:**

In `main()`, import `paused_page_handler` from `queue_handlers` and register:

```python
app.routes.insert(0, Route("/paused", paused_page_handler, methods=["GET"]))
```

Place this alongside the existing `/queue` route registration.

**Verification:**

Run: `uv run python -c "from promptgrimoire import main; print('import ok')"`
Expected: `import ok` (no import errors)

**Commit:** `feat(idle): register /paused route in app`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Unit tests for /paused handler

**Verifies:** idle-tab-eviction-471.AC3.1, idle-tab-eviction-471.AC3.4, idle-tab-eviction-471.AC3.5, idle-tab-eviction-471.AC3.6

**Files:**
- Create: `tests/unit/test_paused_page.py`

**Testing:**

Follow the existing pattern from `tests/unit/test_queue_page.py`:

- Create a Starlette `TestClient` fixture with just the `/paused` route
- Group tests into classes by concern:

**TestPausedPageStructure:**
- idle-tab-eviction-471.AC3.6: `GET /paused` returns 200 with `text/html` content type
- Response contains "paused" and "inactivity" text

**TestPausedPageReturnUrl:**
- idle-tab-eviction-471.AC3.1: `GET /paused?return=/annotation/some-uuid` — Resume link href is `/annotation/some-uuid`
- idle-tab-eviction-471.AC3.5: `GET /paused` (no return param) — Resume link href is `/`
- idle-tab-eviction-471.AC3.1: `GET /paused?return=/courses/123` — Resume link href is `/courses/123`

**TestPausedPageOpenRedirectGuard:**
- idle-tab-eviction-471.AC3.4: `GET /paused?return=https://evil.com` — Resume link href is `/`
- idle-tab-eviction-471.AC3.4: `GET /paused?return=//evil.com` — Resume link href is `/`
- idle-tab-eviction-471.AC3.4: `GET /paused?return=javascript:alert(1)` — Resume link href is `/`

**TestPausedPageXSSPrevention:**
- Return URL with HTML entities is properly escaped in href attribute

**Verification:**

Run: `uv run grimoire test run tests/unit/test_paused_page.py`
Expected: All tests pass

**Commit:** `test(idle): add /paused handler unit tests`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
