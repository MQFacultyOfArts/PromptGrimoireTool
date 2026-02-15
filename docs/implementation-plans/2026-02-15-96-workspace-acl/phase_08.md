# Workspace ACL Implementation Plan — Phase 8

**Goal:** Add access guards at page entry points and real-time revocation via NiceGUI's connected client registry.

**Architecture:** A `check_workspace_access()` function in `auth/__init__.py` combines `is_privileged_user()` (admin bypass) with `resolve_permission()` (Phase 4 ACL resolution). Enforcement guards are added at the top of `_render_workspace_view()` in `pages/annotation/workspace.py` and the page entry of roleplay.py. Revocation uses the existing `_workspace_presence` registry (`pages/annotation/__init__.py:114`) to push redirects via `Client.run_javascript()` (cross-client communication — NiceGUI's native `ui.notify()`/`ui.navigate.to()` only work in the current client context).

**Tech Stack:** SQLModel, PostgreSQL, NiceGUI

**Scope:** 8 phases from original design (this is phase 8 of 8)

**Codebase verified:** 2026-02-15

**Module structure:** The annotation page is a 12-module package (`pages/annotation/`). Key targets: `workspace.py` has `_render_workspace_view()` (line 621), `broadcast.py` has `_setup_client_sync()` (line 94), `__init__.py` has `_RemotePresence` (line 81) and `_workspace_presence` (line 114).

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 96-workspace-acl.AC10: Enforcement and revocation
- **96-workspace-acl.AC10.1 Success:** Unauthenticated user accessing a workspace URL is redirected to /login
- **96-workspace-acl.AC10.2 Success:** Unauthorised user accessing a workspace URL is redirected to /courses with notification
- **96-workspace-acl.AC10.3 Success:** Authorised user with viewer permission sees read-only UI
- **96-workspace-acl.AC10.4 Success:** Authorised user with editor/owner permission sees full edit UI
- **96-workspace-acl.AC10.5 Success:** Revoking access pushes immediate redirect to the connected client via websocket
- **96-workspace-acl.AC10.6 Success:** Revoked user sees toast notification "Your access has been revoked"
- **96-workspace-acl.AC10.7 Edge:** User with no active websocket connection — revocation takes effect on next page load

Also verifies from Phase 4:
- **96-workspace-acl.AC6.6:** Admin (via Stytch) gets owner-level access regardless of ACL/enrollment
- **96-workspace-acl.AC6.9:** User with no auth session gets None

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add check_workspace_access() to auth/__init__.py

**Verifies:** 96-workspace-acl.AC6.6, 96-workspace-acl.AC6.9, 96-workspace-acl.AC10.1, 96-workspace-acl.AC10.2

**Files:**
- Modify: `src/promptgrimoire/auth/__init__.py`

**Implementation:**

Add `check_workspace_access()` that combines the admin bypass with ACL resolution:

```python
async def check_workspace_access(
    workspace_id: UUID,
    auth_user: dict[str, object] | None,
) -> str | None:
    """Check if the current user can access a workspace.

    Resolution order:
    1. No auth_user → None (unauthenticated)
    2. Admin (is_privileged_user) → "owner" (bypass)
    3. ACL resolution via can_access_workspace() → permission or None

    Args:
        workspace_id: The workspace UUID.
        auth_user: The auth_user dict from app.storage.user, or None.

    Returns:
        Permission name ("owner", "editor", "viewer") or None if denied.
    """
    if auth_user is None:
        return None

    # Admin bypass — privileged users get owner-level access
    if is_privileged_user(auth_user):
        return "owner"

    # ACL resolution
    user_id_str = auth_user.get("user_id")
    if not user_id_str:
        return None

    from uuid import UUID as _UUID

    from promptgrimoire.db.acl import can_access_workspace

    user_id = _UUID(str(user_id_str))
    return await can_access_workspace(workspace_id, user_id)
```

Add `check_workspace_access` to the module's `__all__` list and exports.

**Verification:**

Run: `uv run python -c "from promptgrimoire.auth import check_workspace_access; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add check_workspace_access() combining admin bypass with ACL resolution`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add enforcement guard to annotation workspace view

**Verifies:** 96-workspace-acl.AC10.1, 96-workspace-acl.AC10.2, 96-workspace-acl.AC10.3, 96-workspace-acl.AC10.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py`

**Implementation:**

Add an access guard at the top of `_render_workspace_view()` (line 621, before the workspace load):

```python
async def _render_workspace_view(workspace_id: UUID, client: Client) -> None:
    """Render the workspace content view with documents or add content form."""
    # --- ACL enforcement guard ---
    auth_user = app.storage.user.get("auth_user")
    permission = await check_workspace_access(workspace_id, auth_user)

    if auth_user is None:
        ui.navigate.to("/login")
        return

    if permission is None:
        ui.notify("You do not have access to this workspace", type="negative")
        ui.navigate.to("/courses")
        return

    # Permission level determines UI mode
    read_only = permission == "viewer"

    # --- existing code continues ---
    workspace = await get_workspace(workspace_id)
    # ...
```

Add import at top of `workspace.py` (alongside the existing `from promptgrimoire.auth import is_privileged_user`):
```python
from promptgrimoire.auth import check_workspace_access, is_privileged_user
```

The `read_only` flag must be threaded through to the rendering functions that control edit controls:
- When `read_only=True`: hide the Milkdown editor, hide highlight creation buttons, disable comment submission, show "View Only" badge
- When `read_only=False`: full editor UI (existing behaviour)

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.annotation.workspace import _render_workspace_view; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add ACL enforcement guard to annotation workspace view`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add enforcement guard to roleplay.py

**Verifies:** 96-workspace-acl.AC10.1, 96-workspace-acl.AC10.2

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py`

**Implementation:**

The roleplay page (roleplay.py:169) currently has no auth check. Add a basic auth guard at the page entry:

```python
@page_route("/roleplay", title="Roleplay", icon="chat", order=30)
async def roleplay_page() -> None:
    """Roleplay chat page."""
    await ui.context.client.connected()

    # Auth guard — require login
    auth_user = app.storage.user.get("auth_user")
    if auth_user is None:
        ui.navigate.to("/login")
        return

    # ... existing page content ...
```

Note: The roleplay page currently doesn't load workspaces, so there's no workspace-level ACL check. This guard just ensures authentication. When roleplay gains persistent session storage (future work), workspace-level checks should be added.

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.roleplay import *; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: add auth guard to roleplay page`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement revocation broadcast

**Verifies:** 96-workspace-acl.AC10.5, 96-workspace-acl.AC10.6, 96-workspace-acl.AC10.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` (add `user_id` field to `_RemotePresence`)
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py` (populate `user_id` in `_setup_client_sync()`, add `revoke_and_redirect()`)

**Implementation:**

Add a `revoke_and_redirect()` function that pushes a redirect + toast to connected clients when access is revoked. This uses the existing `_workspace_presence` registry (`__init__.py:114`).

**Why `run_javascript()`:** This function pushes notifications to a *different* client (the revoked user), not the current client. NiceGUI's `ui.notify()` and `ui.navigate.to()` only work within the current client context. For cross-client communication, `Client.run_javascript()` is the correct NiceGUI API. The `Quasar.Notify.create()` call matches NiceGUI's own notification implementation.

**Step 1:** Add `user_id: str | None = None` field to `_RemotePresence` in `__init__.py` (line 81). Add after `has_milkdown_editor` (line 95):

```python
@dataclass
class _RemotePresence:
    """Lightweight presence state for a connected client."""
    # ... existing fields ...
    has_milkdown_editor: bool = False
    user_id: str | None = None
```

**Step 2:** Populate `user_id` during client registration in `_setup_client_sync()` (`broadcast.py:94`). After the existing client setup code, add:

```python
# Store user_id for revocation lookup
auth_user = app.storage.user.get("auth_user")
if auth_user:
    presence.user_id = str(auth_user.get("user_id", ""))
```

**Step 3:** Add the `revoke_and_redirect()` function to `broadcast.py`:

```python
async def revoke_and_redirect(
    workspace_id: UUID, user_id: UUID
) -> int:
    """Revoke access and redirect the user if they are connected.

    Finds all connected clients for this user in this workspace's presence
    registry, sends a toast notification and redirect via run_javascript()
    on the remote client.

    Note: run_javascript() is necessary here because we are pushing to a
    different client (the revoked user), not the current client. NiceGUI's
    ui.notify()/ui.navigate.to() only work in the current client context.

    Args:
        workspace_id: The workspace UUID.
        user_id: The user UUID whose access was revoked.

    Returns:
        Number of connected clients that were notified.
    """
    workspace_key = str(workspace_id)
    notified = 0

    if workspace_key not in _workspace_presence:
        return 0

    # Find clients belonging to this user
    clients_to_remove: list[str] = []
    for client_id, presence in _workspace_presence[workspace_key].items():
        if presence.user_id == str(user_id):
            clients_to_remove.append(client_id)

    for client_id in clients_to_remove:
        presence = _workspace_presence[workspace_key].get(client_id)
        if presence and presence.nicegui_client is not None:
            with contextlib.suppress(Exception):
                await presence.nicegui_client.run_javascript(
                    'Quasar.Notify.create({type: "negative", message: "Your access has been revoked"}); '
                    'window.location.href = "/courses";',
                    timeout=2.0,
                )
                notified += 1

        # Remove from registry
        _workspace_presence[workspace_key].pop(client_id, None)

    # Clean up empty workspace dict
    if workspace_key in _workspace_presence and not _workspace_presence[workspace_key]:
        del _workspace_presence[workspace_key]

    return notified
```

**Note on AC10.7:** If the user has no active websocket connection (not in `_workspace_presence`), the function returns 0. The revocation takes effect on next page load because `_render_workspace_view()` re-checks permissions via `check_workspace_access()` every time the page loads.

**Verification:**

Run: `uv run python -c "from promptgrimoire.pages.annotation.broadcast import revoke_and_redirect; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: implement revocation broadcast via connected client registry`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Wire revocation into revoke_permission()

**Files:**
- Modify: `src/promptgrimoire/db/acl.py`

**Implementation:**

Update `revoke_permission()` (from Phase 3) to optionally trigger the revocation broadcast. Add an `on_revoke` callback parameter:

```python
async def revoke_permission(
    workspace_id: UUID,
    user_id: UUID,
    *,
    on_revoke: Callable[[UUID, UUID], Awaitable[int]] | None = None,
) -> bool:
    """Revoke a user's permission on a workspace.

    Returns True if an entry was deleted, False if no entry existed.
    If on_revoke is provided and an entry was deleted, calls on_revoke(workspace_id, user_id)
    to notify connected clients.
    """
    async with get_session() as session:
        entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == workspace_id,
                ACLEntry.user_id == user_id,
            )
        )
        row = entry.one_or_none()
        if row is None:
            return False
        await session.delete(row)
        await session.flush()

    if on_revoke is not None:
        await on_revoke(workspace_id, user_id)

    return True
```

The `on_revoke` callback is optional -- existing callers (tests, etc.) are unaffected. The page layer passes `revoke_and_redirect` when revoking from the UI. Since ACLEntry links directly to Workspace via `workspace_id`, no workspace lookup is needed to pass the ID to the callback.

**Verification:**

Run: `uv run python -c "from promptgrimoire.db.acl import revoke_permission; print('OK')"`
Expected: Imports succeed.

**Commit:** `feat: wire revocation broadcast into revoke_permission() via callback`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration and E2E tests for enforcement and revocation

**Verifies:** 96-workspace-acl.AC6.6, 96-workspace-acl.AC6.9, 96-workspace-acl.AC10.1, 96-workspace-acl.AC10.2, 96-workspace-acl.AC10.3, 96-workspace-acl.AC10.4, 96-workspace-acl.AC10.5, 96-workspace-acl.AC10.6, 96-workspace-acl.AC10.7

**Files:**
- Create: `tests/integration/test_enforcement.py`

**Implementation:**

Integration tests using real PostgreSQL. Include skip guard.

Tests:

- **AC6.6:** Create an admin auth_user dict (`is_admin=True`). Call `check_workspace_access(workspace_id, admin_auth_user)`. Verify returns `"owner"` regardless of ACL entries.

- **AC6.9:** Call `check_workspace_access(workspace_id, None)`. Verify returns `None`.

- **AC10.1:** Call `check_workspace_access(workspace_id, None)`. Verify returns `None`. (Page layer redirects to `/login` — tested at integration level via the return value.)

- **AC10.2:** Create a user with no ACL entry. Call `check_workspace_access(workspace_id, user_auth_dict)`. Verify returns `None`. (Page layer redirects to `/courses` — tested at integration level.)

- **AC10.3:** Grant viewer permission to user. Call `check_workspace_access(workspace_id, user_auth_dict)`. Verify returns `"viewer"`. (Page layer renders read-only UI.)

- **AC10.4:** Grant editor permission to user. Call `check_workspace_access(workspace_id, user_auth_dict)`. Verify returns `"editor"`. Grant owner permission. Verify returns `"owner"`. (Page layer renders full UI.)

- **AC10.5 & AC10.6:** These require E2E testing with actual connected clients. Defer to E2E test suite. For now, test `revoke_and_redirect()` returns 0 when no clients are connected (AC10.7).

- **AC10.7:** Call `revoke_and_redirect(workspace_id, user_id)` when no entry exists in `_workspace_presence`. Verify returns 0.

**Testing:**

Run: `uv run pytest tests/integration/test_enforcement.py -v`
Expected: All tests pass.

Run: `uv run test-all`
Expected: All existing tests pass alongside new enforcement tests.

**Commit:** `test: add integration tests for enforcement and revocation`

<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->
