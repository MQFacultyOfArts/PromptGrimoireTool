# Roleplay Privileged Access Implementation Plan - Phase 2: Shared Page Guard

**Goal:** Deny non-privileged direct access to roleplay-marked pages in place, while preserving privileged access and existing login/feature-flag behavior.

**Architecture:** Add a shared page-entry helper in `src/promptgrimoire/pages/layout.py` that enforces the approved short-term rule: unauthenticated users are sent to `/login`, authenticated non-privileged users get a negative notification and no redirect, privileged users continue. Reuse that helper from both `src/promptgrimoire/pages/roleplay.py` and `src/promptgrimoire/pages/logviewer.py` so direct-route protection matches the nav filtering added in Phase 1.

**Tech Stack:** Python 3.14, NiceGUI page functions, pytest unit tests with `unittest.mock`

**Scope:** Phase 2 of 2 from original design

**Codebase verified:** 2026-03-04

**Testing documentation:** `/home/brian/people/Brian/PromptGrimoireTool/AGENTS.md`, `/home/brian/people/Brian/PromptGrimoireTool/docs/testing.md`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-privileged-access-258.AC1: Privileged users retain standalone roleplay access
- **roleplay-privileged-access-258.AC1.1 Success:** Authenticated user where `is_privileged_user(auth_user)` returns `True` can open `/roleplay`
- **roleplay-privileged-access-258.AC1.2 Success:** Existing feature-flag guard still applies before the roleplay UI renders
- **roleplay-privileged-access-258.AC1.3 Success:** Existing unauthenticated behavior is unchanged; unauthenticated user is sent to `/login`

### roleplay-privileged-access-258.AC3: Non-privileged direct access is denied in place
- **roleplay-privileged-access-258.AC3.1 Failure:** Authenticated non-privileged user who opens `/roleplay` receives a negative notification
- **roleplay-privileged-access-258.AC3.2 Failure:** The page exits before rendering upload or chat controls for an authenticated non-privileged user
- **roleplay-privileged-access-258.AC3.3 Success:** Denial does not redirect the user away from `/roleplay`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add unit tests for the shared privileged roleplay guard

**Verifies:** roleplay-privileged-access-258.AC1.3, roleplay-privileged-access-258.AC3.1, roleplay-privileged-access-258.AC3.3

**Files:**
- Create: `tests/unit/test_roleplay_access.py`

**Implementation:**

Create `tests/unit/test_roleplay_access.py` as a new unit-test module covering the shared layout guard behavior directly.

Structure the file with:
- `from __future__ import annotations`
- `from unittest.mock import MagicMock, patch`
- `import pytest`
- imports from `promptgrimoire.pages.layout`

Add a `TestRequirePrivilegedRoleplayUser` class for the new shared helper introduced in Task 2. The helper name in these tests should match the implementation name exactly.

Tests to write:

1. `test_unauthenticated_user_redirects_to_login`
   - Patch the session-user source in `promptgrimoire.pages.layout` to return `None`
   - Patch `promptgrimoire.pages.layout.ui.navigate.to`
   - Assert the helper returns `False`
   - Assert `ui.navigate.to("/login")` is called exactly once
   - Assert `ui.notify` is not called

2. `test_non_privileged_user_gets_negative_notification_without_redirect`
   - Patch session user to a non-privileged auth payload such as `{"is_admin": False, "roles": []}`
   - Patch `promptgrimoire.pages.layout.ui.notify`
   - Patch `promptgrimoire.pages.layout.ui.navigate.to`
   - Assert the helper returns `False`
   - Assert `ui.notify` is called exactly once with `type="negative"`
   - Assert `ui.navigate.to` is not called

3. `test_privileged_user_passes_guard`
   - Patch session user to a privileged auth payload such as `{"is_admin": False, "roles": ["instructor"]}`
   - Patch `ui.notify` and `ui.navigate.to`
   - Assert the helper returns `True`
   - Assert neither notify nor navigate is called

Use direct assertions on side effects; do not involve NiceGUI rendering or page functions in this task.

**Testing:**

Tests must verify each AC listed above:
- roleplay-privileged-access-258.AC1.3: Unauthenticated behavior remains a login redirect
- roleplay-privileged-access-258.AC3.1: Non-privileged direct access produces a negative notification
- roleplay-privileged-access-258.AC3.3: Non-privileged denial does not redirect away

Follow project unit-test patterns:
- synchronous tests for synchronous helpers
- `unittest.mock.patch` for NiceGUI side effects
- descriptive docstrings on each test

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_access.py -v`
Expected: The new helper tests fail before the helper is implemented.

**Commit:** `test: add shared roleplay access guard coverage`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement the shared privileged roleplay guard in layout

**Verifies:** roleplay-privileged-access-258.AC1.3, roleplay-privileged-access-258.AC3.1, roleplay-privileged-access-258.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/layout.py:8-80`
- Modify: `tests/unit/test_roleplay_access.py`

**Implementation:**

In `src/promptgrimoire/pages/layout.py`, add a new helper that combines authentication and privilege checks for roleplay-marked pages.

1. Import:

```python
from promptgrimoire.auth import is_privileged_user
```

2. Add a new helper below `require_roleplay_enabled()`:

```python
def require_privileged_roleplay_user() -> bool:
    """Require an authenticated privileged user for standalone roleplay pages."""
```

3. Implement the helper with this control flow:
- read the current user via the existing `_get_session_user()` helper
- if no user: `ui.navigate.to("/login")`; return `False`
- if `is_privileged_user(user)` is `False`: `ui.notify("Roleplay is restricted", type="negative")`; return `False`
- otherwise return `True`

Do not add a redirect for the non-privileged branch. The denial must stay in place.

Do not fold this into `require_roleplay_enabled()`. Keep feature-flag gating separate from privilege gating so call sites preserve the existing order: feature flag first, then user-access rule.

**Testing:**

Re-run the Task 1 helper tests and confirm all three branches now pass.

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_access.py -v`
Expected: All helper tests pass.

Run: `uv run ruff check src/promptgrimoire/pages/layout.py tests/unit/test_roleplay_access.py`
Expected: No lint errors.

Run: `uv run ruff format src/promptgrimoire/pages/layout.py tests/unit/test_roleplay_access.py --check`
Expected: No formatting changes needed after final edits.

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add shared privileged roleplay guard`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add page-wiring tests for roleplay and logviewer guards

**Verifies:** roleplay-privileged-access-258.AC1.1, roleplay-privileged-access-258.AC1.2, roleplay-privileged-access-258.AC3.2

**Files:**
- Modify: `tests/unit/test_roleplay_access.py`

**Implementation:**

Extend `tests/unit/test_roleplay_access.py` with async page-entry tests that prove the two page modules actually use the shared helper and stop before constructing page-specific UI when access is denied.

Add a `TestRoleplayAndLogsPageWiring` class.

For `roleplay_page()`:

1. `test_roleplay_page_stops_before_page_layout_for_denied_user`
   - Patch `promptgrimoire.pages.roleplay.ui`
   - Set `ui.context.client.connected = AsyncMock()`
   - Patch `promptgrimoire.pages.roleplay.require_roleplay_enabled` to return `True`
   - Patch `promptgrimoire.pages.roleplay.require_privileged_roleplay_user` to return `False`
   - Patch `promptgrimoire.pages.roleplay.page_layout`
   - `await roleplay_page()`
   - Assert `require_privileged_roleplay_user()` is called once
   - Assert `page_layout` is not called

2. `test_roleplay_page_enters_page_layout_for_privileged_user`
   - Patch `ui.context.client.connected = AsyncMock()`
   - Patch `require_roleplay_enabled` to return `True`
   - Patch `require_privileged_roleplay_user` to return `True`
   - Patch `page_layout` with a minimal context-manager mock
   - `await roleplay_page()`
   - Assert `page_layout("Roleplay")` is entered

3. `test_roleplay_page_stops_before_access_guard_when_feature_flag_disabled`
   - Patch `require_roleplay_enabled` to return `False`
   - Assert `require_privileged_roleplay_user` is not called
   - This is the direct regression for AC1.2’s ordering requirement

For `logs_page()`:

4. `test_logs_page_stops_before_label_render_for_denied_user`
   - Patch `promptgrimoire.pages.logviewer.ui`
   - Set `ui.context.client.connected = AsyncMock()`
   - Patch `promptgrimoire.pages.logviewer.require_roleplay_enabled` to return `True`
   - Patch `promptgrimoire.pages.logviewer.require_privileged_roleplay_user` to return `False`
   - `await logs_page()`
   - Assert `ui.label` is not called

The logs-page test is not directly tied to a design-plan AC, but it is required to lock in the approved shared-guard decision for all roleplay-marked pages.

**Testing:**

Tests must verify each AC listed above:
- roleplay-privileged-access-258.AC1.1: Privileged user can proceed past the roleplay page’s access gate
- roleplay-privileged-access-258.AC1.2: Feature-flag guard still runs before privilege logic
- roleplay-privileged-access-258.AC3.2: Denied roleplay access exits before upload/chat UI is constructed

Follow project async-test patterns:
- use `@pytest.mark.asyncio` on async tests
- use `AsyncMock` for `ui.context.client.connected`
- patch module-local imports (`promptgrimoire.pages.roleplay...`, `promptgrimoire.pages.logviewer...`) rather than original source modules

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_access.py -v`
Expected: The new page-wiring tests fail before the page modules are updated to call the shared helper.

**Commit:** `test: add roleplay page access wiring coverage`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Wire the shared guard into roleplay and logviewer pages

**Verifies:** roleplay-privileged-access-258.AC1.1, roleplay-privileged-access-258.AC1.2, roleplay-privileged-access-258.AC1.3, roleplay-privileged-access-258.AC3.1, roleplay-privileged-access-258.AC3.2, roleplay-privileged-access-258.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py:18-190`
- Modify: `src/promptgrimoire/pages/logviewer.py:15-125`
- Modify: `tests/unit/test_roleplay_access.py`

**Implementation:**

Update both roleplay-marked page modules to use the shared helper from Task 2.

In `src/promptgrimoire/pages/roleplay.py`:
- import `require_privileged_roleplay_user` from `promptgrimoire.pages.layout`
- keep the current order:
  1. `await ui.context.client.connected()`
  2. `if not require_roleplay_enabled(): return`
  3. `if not require_privileged_roleplay_user(): return`
- remove the inline `auth_user = app.storage.user.get("auth_user")` login gate, because the shared helper now owns auth-plus-privilege handling
- after the guard, keep the rest of the page behavior unchanged

In `src/promptgrimoire/pages/logviewer.py`:
- import `require_privileged_roleplay_user` from `promptgrimoire.pages.layout`
- after `require_roleplay_enabled()`, add:

```python
    if not require_privileged_roleplay_user():
        return
```

This closes the currently broader direct-access path on `/logs` so it matches the nav filtering implemented in Phase 1.

Do not add redirects for the non-privileged branch. The negative-notification behavior comes from the shared helper.

**Testing:**

Re-run the full `tests/unit/test_roleplay_access.py` suite and confirm:
- helper behavior passes
- roleplay page ordering is correct
- denied roleplay path does not enter `page_layout`
- privileged roleplay path does enter `page_layout`
- denied logs path does not render page labels

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_access.py -v`
Expected: All roleplay access tests pass.

Run: `uv run ruff check src/promptgrimoire/pages/layout.py src/promptgrimoire/pages/roleplay.py src/promptgrimoire/pages/logviewer.py tests/unit/test_roleplay_access.py`
Expected: No lint errors.

Run: `uv run ruff format src/promptgrimoire/pages/layout.py src/promptgrimoire/pages/roleplay.py src/promptgrimoire/pages/logviewer.py tests/unit/test_roleplay_access.py --check`
Expected: No formatting changes needed after final edits.

Run: `uvx ty check`
Expected: No type errors.

Run: `uv run test-all`
Expected: No regressions in the broader unit/integration suite.

**Commit:** `feat: guard direct roleplay pages for privileged users only`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
