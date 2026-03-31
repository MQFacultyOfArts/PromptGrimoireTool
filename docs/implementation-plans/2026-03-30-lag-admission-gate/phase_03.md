# Lag-Based Admission Gate Implementation Plan

**Goal:** Admission gate check in the `page_route` decorator — gate new users when server is at capacity, redirect to queue page.

**Architecture:** Insert gate check between existing ban check and client registration in `_with_log_context`. Uses admission module from Phase 1, follows same redirect pattern as ban check.

**Tech Stack:** Python 3.14, NiceGUI (ui.navigate.to), urllib.parse

**Scope:** 5 phases from original design (phase 3 of 5)

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

This phase implements and tests:

### lag-admission-gate.AC3: Gate only affects new authenticated users
- **lag-admission-gate.AC3.1 Success:** User already in `client_registry._registry` passes through gate freely (page navigation while admitted)
- **lag-admission-gate.AC3.2 Success:** Privileged users (`is_privileged_user`) bypass gate regardless of cap
- **lag-admission-gate.AC3.3 Failure:** New authenticated user redirected to `/queue?t=<token>&return=<url>` when admitted count >= cap
- **lag-admission-gate.AC3.4 Edge:** User who disconnects and reconnects within 15s `reconnect_timeout` remains in `_registry` and is not gated
- **lag-admission-gate.AC3.5 Success:** User with valid entry ticket passes through gate; ticket is consumed on use
- **lag-admission-gate.AC3.6 Success:** User still in queue is redirected to `/queue?t=<existing_token>` preserving their position

---

<!-- START_TASK_1 -->
### Task 1: Admission gate check in page_route

**Verifies:** lag-admission-gate.AC3.1, lag-admission-gate.AC3.2, lag-admission-gate.AC3.3, lag-admission-gate.AC3.5, lag-admission-gate.AC3.6

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py` (insert gate check at lines 208-209, between ban check and client registration)
- Create: `tests/unit/test_admission_gate.py`

**Implementation:**

Add a `_check_admission_gate` function in `registry.py` following the same pattern as `_check_ban`. The function:

1. Converts `user_id` string to UUID
2. Checks `client_registry._registry` membership → return False (pass through)
3. Checks `admission.try_enter(user_id)` → return False (ticket consumed, pass through)
4. Checks `is_privileged_user(auth_user)` → return False (staff bypass)
5. Checks `len(client_registry._registry) < admission.get_admission_state().cap` → return False (under cap)
6. Checks if user already in queue → get existing token
7. Otherwise enqueue → get new token
8. Build redirect URL: `/queue?t=<token>&return=<url-encoded current path>`
9. `ui.navigate.to(redirect_url)` → return True

The `auth_user` dict is available from `app.storage.user.get("auth_user")` — same source used by the privileged check. The current request path comes from `ui.context.client.page.path` or the `route` parameter already passed to `_with_log_context`.

In `_with_log_context`, after the ban check block (line 207) and before client registration (line 210):

```python
# Admission gate check (after ban, before client registration)
if user_id and await _check_admission_gate(user_id, auth_user, route):
    return
```

Where `auth_user` is the `app.storage.user.get("auth_user")` dict already extracted at line 173.

**Startup race guard:** `_check_admission_gate` must wrap `get_admission_state()` in a try/except `RuntimeError`. If admission state is not yet initialised (page load arrives before `init_admission()` during startup), treat it as "gate open" — return False (pass through). This window is brief (startup only) and safe (no cap restriction means all users enter, which is the pre-feature behaviour).

**Return URL:** Use `ui.context.client.request.url.path` to get the actual resolved request path (e.g. `/annotation/abc-123`), NOT the `route` parameter which is the template (e.g. `/annotation/{workspace_id}`). The resolved path is safe — it comes from NiceGUI's Starlette routing layer, is always a relative path starting with `/`, and cannot be an absolute URL, protocol-relative, or `javascript:` scheme.

**Testing:**

Test file: `tests/unit/test_admission_gate.py`

Tests mock the admission module and client_registry to test each gate path in isolation:

- lag-admission-gate.AC3.1: Mock `_registry` to contain the user_id. Verify gate returns False (pass through), no redirect called.
- lag-admission-gate.AC3.2: Mock empty registry, no ticket, `is_privileged_user` returns True. Verify gate returns False.
- lag-admission-gate.AC3.3: Mock empty registry, no ticket, not privileged, admitted count >= cap. Verify `enqueue()` called and `ui.navigate.to` called with `/queue?t=...&return=...`.
- lag-admission-gate.AC3.5: Mock empty registry, `try_enter` returns True. Verify gate returns False (ticket consumed).
- lag-admission-gate.AC3.6: Mock empty registry, no ticket, not privileged, user already in queue (enqueue returns existing token). Verify redirect uses same token.

Note: AC3.4 (reconnect_timeout) is inherently tested by AC3.1 — if the user is still in `_registry` after reconnect, the gate passes them through. The 15s timeout is a NiceGUI property, not something the gate controls.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_admission_gate.py`
Expected: All tests pass

Run: `uv run grimoire test all`
Expected: All tests pass

Run: `uv run complexipy src/promptgrimoire/pages/registry.py --max-complexity-allowed 15`
Expected: No functions exceed complexity threshold. If `_check_admission_gate` or `_with_log_context` exceeds 15, extract helper functions.

**Commit:** `feat: add admission gate check in page_route decorator`
<!-- END_TASK_1 -->
