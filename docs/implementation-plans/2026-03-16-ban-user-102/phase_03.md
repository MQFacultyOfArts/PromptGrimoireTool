# Ban User Implementation Plan — Phase 3: Client Registry & Real-Time Kick

**Goal:** Track connected clients per user and disconnect banned users immediately via JavaScript redirect.

**Architecture:** Module-level `dict[UUID, set[Client]]` in `auth/client_registry.py` mapping `user_id → {Client, ...}`. Registration in `page_route` wrapper. Deregistration via `client.on_delete`. `disconnect_user()` uses `client.run_javascript('window.location.href = "/banned"')` — NOT `ui.navigate.to()` (which only works for current client context) and NOT `app.sio.disconnect()` (NiceGUI abstracts Socket.IO entirely).

**Tech Stack:** NiceGUI (Client, ui.context.client, client.run_javascript)

**Scope:** Phase 3 of 5 from original design

**Codebase verified:** 2026-03-16

**Design plan correction:** The design plan specified `ui.navigate.to("/banned")` then `app.sio.disconnect(client_id)`. Investigation reveals `app.sio` is never used in this codebase and `ui.navigate.to()` only works for the current client context. The correct approach, proven by `revoke_and_redirect()` in `src/promptgrimoire/pages/annotation/broadcast.py:440-494`, is `client.run_javascript('window.location.href = "/banned"')`.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ban-user-102.AC2: Real-time client disconnection
- **ban-user-102.AC2.1 Success:** Client registry correctly tracks `user_id → client_id` mapping when user loads a page
- **ban-user-102.AC2.2 Success:** Client registry removes mapping when client is deleted (permanent disconnect)
- **ban-user-102.AC2.3 Success:** `disconnect_user()` navigates all of a user's active clients to `/banned` and disconnects them

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create client registry module

**Verifies:** ban-user-102.AC2.1, ban-user-102.AC2.2, ban-user-102.AC2.3

**Files:**
- Create: `src/promptgrimoire/auth/client_registry.py`

**Implementation:**

Create a module-level registry following the `_workspace_presence` pattern in `src/promptgrimoire/pages/annotation/broadcast.py:370-392`.

The module needs:

1. **Module-level dict:** `_registry: dict[UUID, set[Client]] = {}` mapping `user_id → {Client, ...}`. Import `Client` from `nicegui` (check exact import path — likely `from nicegui import Client`).

2. **`register(user_id: UUID, client: Client) -> None`:** Add the client to the user's set. Create the set if it doesn't exist. Also register `client.on_delete` to call `deregister()` on permanent disconnect.

3. **`deregister(user_id: UUID, client: Client) -> None`:** Remove the client from the user's set. Remove the user's entry entirely if the set becomes empty. Tolerate the client not being in the registry (stale state).

4. **`disconnect_user(user_id: UUID) -> int`:** Iterate the user's client set, call `client.run_javascript('window.location.href = "/banned"', timeout=2.0)` on each. Return count of clients where `run_javascript` succeeded without exception (i.e., clients that were successfully redirected). Tolerate errors (client may already be gone — log warning and continue). Clear the user's registry entry after iteration.

Follow the `revoke_and_redirect()` pattern at `broadcast.py:440-494` for error handling around `run_javascript()`:
- Wrap each `run_javascript` call in try/except
- Log warnings for failed redirects
- Continue to next client on failure

Use `structlog.get_logger()` for logging.

**Testing:**

Unit tests for the registry (no database needed, can mock Client objects):
- ban-user-102.AC2.1: `register(user_id, client)` adds to registry, verify with internal state
- ban-user-102.AC2.2: `deregister(user_id, client)` removes from registry; after last client removed, user entry is gone
- ban-user-102.AC2.3: `disconnect_user(user_id)` calls `run_javascript` on all registered clients

Place in `tests/unit/test_client_registry.py`. Mock the `Client` objects.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `feat(auth): add client registry for tracking user connections`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Integrate registration in `page_route` wrapper

**Verifies:** ban-user-102.AC2.1

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py` (the `_with_log_context` wrapper, around lines 128-142)

**Implementation:**

In the `page_route` wrapper function at `src/promptgrimoire/pages/registry.py`, after the ban check added in Phase 2, add client registration:

1. Access `client = ui.context.client` (NiceGUI provides this in page handler context)
2. If `user_id` is not None (user is authenticated):
   - Call `client_registry.register(user_id, client)` to track the connection
3. Import `from promptgrimoire.auth.client_registry import register` and `from nicegui import ui`

The `register()` function already sets up `client.on_delete` for deregistration, so no additional cleanup code is needed in the wrapper.

**Note:** `ui.context.client` is available inside the `_with_log_context` wrapper because it runs in the request context of a `@ui.page` function.

**Testing:**

Integration test verifying that loading a `page_route` page with an authenticated user triggers registration. This may be better covered by Phase 3 Task 1's unit tests (which test `register()` directly) plus the E2E test in Phase 4 (which tests the full flow).

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All existing tests still pass (no regressions from adding registration).

**Commit:** `feat(auth): integrate client registry in page_route wrapper`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify disconnect tolerates stale clients

**Verifies:** ban-user-102.AC2.3 (edge case: stale entries)

**Files:**
- Modify: `tests/unit/test_client_registry.py` (add test case)

**Testing:**

Add a test that registers clients, then has one client's `run_javascript` raise an exception (simulate stale/disconnected client). Verify:
- `disconnect_user()` continues to the next client despite the error
- All remaining clients still get the redirect call
- Return count reflects only successful notifications
- No exceptions propagate

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `test(auth): verify disconnect_user tolerates stale clients`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. Start the app: `uv run run.py`
2. Log in as a test student in two separate browser tabs
3. In a Python shell, call `set_banned(user_id, True)` then `disconnect_user(user_id)`
4. Verify: both browser tabs navigate to `/banned` within 2 seconds
5. Verify: `/banned` page displays "Your account has been suspended. Contact your instructor."
6. Verify: navigating back to `/` redirects back to `/banned`

## Evidence Required
- [ ] Test output showing green for all client_registry tests
- [ ] Manual observation of tab redirect during ban
