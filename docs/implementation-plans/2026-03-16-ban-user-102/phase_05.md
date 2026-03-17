# Ban User Implementation Plan — Phase 5: CLI Commands

**Goal:** `admin ban`, `admin unban`, and `admin ban --list` CLI commands with Stytch metadata update, session revocation, and kick endpoint call.

**Architecture:** Follows `_cmd_instructor()` pattern exactly. Ban flow: `_require_user()` → `set_banned()` → `_update_stytch_metadata()` → `revoke_member_sessions()` → `httpx.post()` kick endpoint. Unban reverses DB + Stytch state only (no kick needed). `--list` displays Rich table. Session revocation requires adding `revoke_member_sessions()` to `AuthClientProtocol`.

**Tech Stack:** Typer, Rich, httpx, Stytch B2B SDK

**Scope:** Phase 5 of 5 from original design

**Codebase verified:** 2026-03-16

**External dependency findings:**
- ✓ Stytch B2B SDK: `client.sessions.revoke(member_id=...)` revokes ALL sessions for a member
- ✓ Method not yet in AuthClientProtocol — needs adding to protocol, client, and mock

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ban-user-102.AC1: Ban command sets persistent state
- **ban-user-102.AC1.3 Success:** `admin ban <email>` updates Stytch `trusted_metadata.banned` to `"true"`
- **ban-user-102.AC1.4 Success:** `admin unban <email>` clears Stytch `trusted_metadata.banned` to `""`
- **ban-user-102.AC1.5 Failure:** `admin ban <nonexistent@email>` exits with error, no DB or Stytch changes

### ban-user-102.AC4: Stytch session revocation
- **ban-user-102.AC4.1 Success:** `admin ban <email>` revokes all active Stytch sessions for the member
- **ban-user-102.AC4.2 Failure:** Ban command with user missing `stytch_member_id` warns but continues (local DB ban still applied)
- **ban-user-102.AC4.3 Success:** After ban, user cannot obtain a new Stytch session (Stytch metadata + revocation prevents re-auth)

### ban-user-102.AC5: List banned users
- **ban-user-102.AC5.3 Success:** Unbanned user no longer appears in `--list` output

---

<!-- START_TASK_1 -->
### Task 1: Add `revoke_member_sessions()` to auth layer

**Verifies:** ban-user-102.AC4.1, ban-user-102.AC4.2

**Files:**
- Modify: `src/promptgrimoire/auth/protocol.py` (add method to `AuthClientProtocol`)
- Modify: `src/promptgrimoire/auth/client.py` (implement in `StytchB2BClient`)
- Modify: `src/promptgrimoire/auth/mock.py` (implement in `MockAuthClient`)

**Implementation:**

Add to `AuthClientProtocol` in `protocol.py`:

```python
async def revoke_member_sessions(self, *, member_id: str) -> SessionResult:
    """Revoke all active sessions for a member."""
    ...
```

Implement in `StytchB2BClient` in `client.py`:
- Call `self._client.sessions.revoke(member_id=member_id)` (or the async variant)
- Return a `SessionResult` with success/failure

Implement in `MockAuthClient` in `mock.py`:
- Clear the member's sessions from `self._active_sessions`
- Return `SessionResult(valid=True)` on success

Follow the existing pattern for other auth methods in these files.

**Testing:**

- ban-user-102.AC4.1: Call `revoke_member_sessions(member_id=...)` — verify mock clears sessions
- ban-user-102.AC4.2: Call `_cmd_ban()` with user missing `stytch_member_id` — verify warning printed but ban still applied

Unit tests in `tests/unit/test_auth_revoke.py` or added to existing `test_manage_users.py`.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `feat(auth): add revoke_member_sessions to AuthClientProtocol`

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: Implement `_cmd_ban()` and `_cmd_unban()` handlers

**Verifies:** ban-user-102.AC1.3, ban-user-102.AC1.4, ban-user-102.AC1.5, ban-user-102.AC4.1, ban-user-102.AC4.2

**Files:**
- Modify: `src/promptgrimoire/cli/admin.py` (add handler functions and Typer commands)

**Implementation:**

Follow the `_cmd_instructor()` pattern at `cli/admin.py:224-244`:

**`_cmd_ban()` handler:**
1. `user = await _require_user(email, con)` — exits with error if not found (AC1.5)
2. `await set_banned(user.id, True)` — set DB ban state (AC1.1 from Phase 1)
3. `await _update_stytch_metadata(user, {"banned": "true"}, console=con)` — update Stytch metadata (AC1.3)
4. If `user.stytch_member_id`: call `auth_client.revoke_member_sessions(member_id=user.stytch_member_id)` (AC4.1). If missing: warn but continue (AC4.2)
5. Call kick endpoint via `httpx.post()`:
   ```python
   async with httpx.AsyncClient(timeout=10.0) as client:
       resp = await client.post(
           f"http://localhost:{port}/api/admin/kick",
           json={"user_id": str(user.id)},
           headers={"Authorization": f"Bearer {secret}"},
       )
   ```
   Read `ADMIN__ADMIN_API_SECRET` from settings. Read port from settings or default 8080. Wrap in try/except — warn on failure but don't abort.
6. Print Rich success message with kicked count from response

**`_cmd_unban()` handler:**
1. `user = await _require_user(email, con)` — exits with error if not found
2. `await set_banned(user.id, False)` — clear DB ban state (AC1.2 from Phase 1)
3. `await _update_stytch_metadata(user, {"banned": ""}, console=con)` — clear Stytch metadata (AC1.4)
4. Print Rich success message. No kick endpoint call needed.

**Typer command registration** (following the `instructor` pattern at lines 387-431):

```python
@admin_app.command("ban")
def ban(
    email: str = typer.Argument(None, help="User email to ban"),
    list_banned: bool = typer.Option(False, "--list", help="List all banned users"),
) -> None:
    """Ban a user or list banned users."""
    if list_banned:
        asyncio.run(_cmd_list_banned())
    elif email:
        asyncio.run(_cmd_ban(email))
    else:
        Console().print("[red]Error:[/] Provide an email or use --list")
        raise typer.Exit(code=1)

@admin_app.command("unban")
def unban(
    email: str = typer.Argument(..., help="User email to unban"),
) -> None:
    """Unban a user."""
    asyncio.run(_cmd_unban(email))
```

**Admin self-ban warning** (from design plan): If the target email belongs to an admin user (`is_admin=True`), print a warning to stderr (e.g., `con.print("[yellow]Warning:[/] target is an admin user")`) but proceed without prompting. The design explicitly says "warn (but not block)" — no interactive confirmation.

**Testing:**

Tests in `tests/unit/test_manage_users.py` (or a new `test_ban_commands.py`), following the two-layer pattern:

Layer 1 (CliRunner):
- ban-user-102.AC1.5: `runner.invoke(app, ["admin", "ban", "nonexistent@email"])` exits with error
- Argument forwarding for ban and unban

Layer 2 (async handler):
- ban-user-102.AC1.3: `_cmd_ban(email)` calls `_update_stytch_metadata` with `{"banned": "true"}`
- ban-user-102.AC1.4: `_cmd_unban(email)` calls `_update_stytch_metadata` with `{"banned": ""}`
- ban-user-102.AC4.1: `_cmd_ban(email)` calls `revoke_member_sessions`
- ban-user-102.AC4.2: `_cmd_ban(email)` with user missing `stytch_member_id` warns but succeeds

Mock all DB functions and Stytch calls. Mock httpx for the kick endpoint call.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `feat(cli): add admin ban and unban commands`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement `_cmd_list_banned()` handler

**Verifies:** ban-user-102.AC5.1, ban-user-102.AC5.2, ban-user-102.AC5.3

**Files:**
- Modify: `src/promptgrimoire/cli/admin.py` (add list handler)

**Implementation:**

Follow the user list Rich table pattern at `cli/admin.py:130-144`:

```python
async def _cmd_list_banned(*, console: Console | None = None) -> None:
    """Display all banned users."""
    con = console or Console()
    users = await get_banned_users()

    if not users:
        con.print("[dim]No banned users.[/]")
        return

    table = Table(title="Banned Users")
    table.add_column("Email", style="cyan")
    table.add_column("Name")
    table.add_column("Banned At")

    for u in users:
        table.add_row(
            u.email,
            u.display_name,
            u.banned_at.strftime("%Y-%m-%d %H:%M UTC") if u.banned_at else "—",
        )

    con.print(table)
```

**Testing:**

- ban-user-102.AC5.1: `_cmd_list_banned()` with banned users shows table with email, name, timestamp
- ban-user-102.AC5.2: `_cmd_list_banned()` with no banned users shows "No banned users." message
- ban-user-102.AC5.3: After unbanning, user no longer appears in list (test ban → list → unban → list)

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Complexipy check:**

```bash
uv run complexipy src/promptgrimoire/cli/admin.py
```

Report any functions near the threshold (complexity 10-15). `admin.py` is a large file.

**Commit:** `feat(cli): add admin ban --list command`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify end-to-end ban flow (integration)

**Verifies:** ban-user-102.AC4.3, ban-user-102.AC5.3

**Files:**
- Create: `tests/integration/test_ban_lifecycle.py`

**Testing:**

Add an integration test (with mocked Stytch but real DB) that exercises the full flow:
1. Create user
2. Ban user → verify DB state, Stytch metadata call, session revocation call
3. List banned → verify user appears
4. Unban user → verify DB state, Stytch metadata call
5. List banned → verify user no longer appears

This covers AC4.3 (after ban, re-auth prevented by metadata + revocation combination) and AC5.3 (unbanned user disappears from list).

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `test(cli): verify full ban/unban lifecycle`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. Seed a test user: `uv run grimoire admin create test-ban@example.com "Test Ban User"`
2. Ban the user: `uv run grimoire admin ban test-ban@example.com`
3. Verify output: should show success with Stytch metadata update and kick result
4. List banned users: `uv run grimoire admin ban --list`
5. Verify: test-ban@example.com appears with `banned_at` timestamp
6. Unban the user: `uv run grimoire admin unban test-ban@example.com`
7. List banned users: `uv run grimoire admin ban --list`
8. Verify: test-ban@example.com no longer appears, shows "No banned users." message

## Evidence Required
- [ ] Test output showing green for all ban CLI tests
- [ ] Screenshot/terminal output of ban → list → unban → list cycle

---

## Documentation Gate

After all tasks pass, update user-facing documentation:

1. Update `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` with ban/unban/--list CLI usage
2. Run `uv run grimoire docs build` and verify clean output
3. Commit documentation changes
