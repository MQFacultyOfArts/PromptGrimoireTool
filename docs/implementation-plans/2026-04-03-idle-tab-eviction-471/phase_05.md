# Idle Tab Eviction Implementation Plan

**Goal:** Pre-auth landing page as lightweight bookmark target for students

**Architecture:** Raw Starlette handler at `/welcome` serving static HTML with a "Login to PromptGrimoire" button. No NiceGUI client, no WebSocket connection. Follows the exact pattern of `/queue` and `/paused` in `queue_handlers.py`. The existing `/` (navigator) flow is unchanged — `/welcome` is a separate, lighter entry point for bookmarks.

**Motivation:** When the server restarts, all students are disconnected. If their browsers have `/` bookmarked, each reload creates a NiceGUI client just to redirect to `/login`. With `/welcome` as the bookmark target, restarts don't flood the server with transient NiceGUI clients.

**Tech Stack:** Starlette (already in use)

**Scope:** 7 phases from original design (phases 1-7, original Phase 5 (Login Page Element Reduction) replaced by pre-auth landing page)

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase implements new acceptance criteria not in the original design:

### idle-tab-eviction-471.AC7: Pre-auth landing page
- **idle-tab-eviction-471.AC7.1 Success:** `GET /welcome` returns static HTML with "Login to PromptGrimoire" button linking to `/login?return=/`
- **idle-tab-eviction-471.AC7.2 Success:** `/welcome` creates no NiceGUI client (raw Starlette handler, no WebSocket)
- **idle-tab-eviction-471.AC7.3 Success:** Clicking Login on `/welcome` navigates to `/login?return=/`, and after authentication returns user to `/`
- **idle-tab-eviction-471.AC7.4 Success:** `/welcome` renders correctly with same visual style as `/paused` and `/queue` pages

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: `/welcome` Starlette handler

**Verifies:** idle-tab-eviction-471.AC7.1, idle-tab-eviction-471.AC7.2, idle-tab-eviction-471.AC7.4

**Files:**
- Modify: `src/promptgrimoire/queue_handlers.py` (add `welcome_page_handler` and `_build_welcome_html`)

**Implementation:**

Add `welcome_page_handler(request: Request) -> HTMLResponse`:
- Return `HTMLResponse(_build_welcome_html())`

Add `_build_welcome_html() -> str`:
- Follow the same inline HTML pattern as `_build_queue_html` and `_build_paused_html`
- Centred card layout with "PromptGrimoire" heading
- Brief welcome text (e.g., "Collaborative prompt annotation for your classroom")
- "Login" button as an `<a>` tag pointing to `/login?return=/`
- Inline CSS matching the queue/paused page styling (system-ui font, flexbox centred, `#f5f5f5` background, `max-width: 400px` card)

**Verification:**

Run: `uv run python -c "from promptgrimoire.queue_handlers import _build_welcome_html; print(_build_welcome_html()[:200])"`
Expected: HTML string containing "PromptGrimoire" and login link

**Commit:** `feat(idle): add /welcome pre-auth landing page`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Route registration for `/welcome`

**Verifies:** idle-tab-eviction-471.AC7.2

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (add `/welcome` route alongside `/queue` and `/paused`)

**Implementation:**

In `main()`, import `welcome_page_handler` from `queue_handlers` and register:

```python
app.routes.insert(0, Route("/welcome", welcome_page_handler, methods=["GET"]))
```

Place this alongside the existing `/queue` and `/paused` route registrations.

**Verification:**

Run: `uv run python -c "from promptgrimoire import main; print('import ok')"`
Expected: No import errors

**Commit:** `feat(idle): register /welcome route in app`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Unit tests for /welcome handler

**Verifies:** idle-tab-eviction-471.AC7.1, idle-tab-eviction-471.AC7.2, idle-tab-eviction-471.AC7.3, idle-tab-eviction-471.AC7.4

**Files:**
- Create: `tests/unit/test_welcome_page.py`

**Testing:**

Follow the existing pattern from `tests/unit/test_queue_page.py` and `tests/unit/test_paused_page.py`:

- Create a Starlette `TestClient` fixture with just the `/welcome` route

**TestWelcomePageStructure:**
- idle-tab-eviction-471.AC7.1: `GET /welcome` returns 200 with `text/html` content type
- idle-tab-eviction-471.AC7.4: Response contains "PromptGrimoire" heading text

**TestWelcomePageLoginLink:**
- idle-tab-eviction-471.AC7.1: Response HTML contains an `<a>` tag with `href` pointing to `/login?return=/`
- idle-tab-eviction-471.AC7.3: The login link includes `return=/` query parameter

**Verification:**

Run: `uv run grimoire test run tests/unit/test_welcome_page.py`
Expected: All tests pass

**Commit:** `test(idle): add /welcome handler unit tests`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
