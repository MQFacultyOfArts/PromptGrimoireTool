# Ban User Implementation Plan — Phase 2: Session Validation Ban Check

**Goal:** Reject banned users at login/re-auth and display a suspension message page.

**Architecture:** Ban check added to the `page_route` decorator wrapper so all protected pages automatically reject banned users. Separate `/banned` page uses `@ui.page()` directly (no `page_route`) to avoid redirect loops. Ban check is DB-only (no Stytch query).

**Tech Stack:** NiceGUI, SQLModel

**Scope:** Phase 2 of 5 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ban-user-102.AC3: Banned user rejected on re-auth
- **ban-user-102.AC3.1 Success:** Banned user attempting session validation is redirected to `/banned` page
- **ban-user-102.AC3.2 Success:** `/banned` page displays "Your account has been suspended. Contact your instructor." with no navigation

---

<!-- START_TASK_1 -->
### Task 1: Create `/banned` page

**Verifies:** ban-user-102.AC3.2

**Files:**
- Create: `src/promptgrimoire/pages/banned.py`

**Implementation:**

Create a minimal page using `@ui.page("/banned")` directly (NOT `@page_route()`). The page should:
- Display "Your account has been suspended. Contact your instructor." prominently
- Have no navigation elements (no sidebar, no header, no links)
- Use `category="hidden"` semantics (the page should not appear in any navigation menus)
- Be accessible without authentication (banned users have no valid session)

Follow the login page pattern at `src/promptgrimoire/pages/auth.py:487-493` for how `@ui.page()` is used directly. The page content should be simple — centered text, no UI framework widgets beyond basic NiceGUI labels.

Ensure the page module is imported so NiceGUI discovers the route. Check how other page modules are imported (likely in `src/promptgrimoire/pages/__init__.py` or via the page registry).

**Testing:**

- ban-user-102.AC3.2: Navigate to `/banned` — page displays suspension message with no navigation controls

This is best tested as an E2E test since it requires a running NiceGUI server. Place in `tests/e2e/test_banned_page.py`.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: Tests pass.

**Commit:** `feat(ui): add /banned suspension page`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add ban check to `page_route` decorator

**Verifies:** ban-user-102.AC3.1

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py` (the `page_route` wrapper function, around lines 128-138)

**Implementation:**

In the `page_route` wrapper function at `src/promptgrimoire/pages/registry.py`, after it reads `auth_user` from `app.storage.user` (around line 133), add a ban check:

1. Extract `user_id` from `auth_user` (it's a UUID in the auth_user dict)
2. If the page requires auth (`requires_auth=True`, which is the default) AND `auth_user` exists:
   - Query the database to check `is_banned` for that `user_id`
   - If banned, navigate to `/banned` and return (do NOT call the page function)
3. If the page does NOT require auth, skip the ban check

Call `is_user_banned(user_id)` from `db/users.py` (created in Phase 1). This is a lightweight scalar query that returns only the boolean flag.

Import: `from promptgrimoire.db.users import is_user_banned`

**Testing:**

- ban-user-102.AC3.1: Banned user loading any `page_route`-protected page is redirected to `/banned`

This needs an E2E test (Playwright, in `tests/e2e/test_ban_redirect.py`) because the ban check is in the `page_route` decorator, which requires a running NiceGUI server with client lifecycle. The test should:
1. Log in as a test user
2. Ban them via direct DB call (`set_banned()`)
3. Navigate to a protected page
4. Verify redirect to `/banned`

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Complexipy check:**

```bash
uv run complexipy src/promptgrimoire/pages/registry.py
```

Report any functions near the threshold (complexity 10-15).

**Commit:** `feat(auth): add ban check to page_route decorator`

<!-- END_TASK_2 -->
