# Ban User (#102) -- Test Requirements

Maps every acceptance criterion to either an automated test or a documented human verification step.

---

## Automated Tests

### AC1: Ban command sets persistent state

| Criterion | Description | Test Type | Test File |
|-----------|-------------|-----------|-----------|
| AC1.1 | `admin ban <email>` sets `is_banned=True` and `banned_at` to current UTC time | Integration | `tests/integration/test_user_ban.py` |
| AC1.2 | `admin unban <email>` sets `is_banned=False` and `banned_at=None` | Integration | `tests/integration/test_user_ban.py` |
| AC1.3 | `admin ban <email>` updates Stytch `trusted_metadata.banned` to `"true"` | Unit | `tests/unit/test_ban_commands.py` |
| AC1.4 | `admin unban <email>` clears Stytch `trusted_metadata.banned` to `""` | Unit | `tests/unit/test_ban_commands.py` |
| AC1.5 | `admin ban <nonexistent@email>` exits with error, no DB or Stytch changes | Unit | `tests/unit/test_ban_commands.py` |

**AC1.1/AC1.2 detail:** Integration tests call `set_banned(user_id, True)` and `set_banned(user_id, False)` against a real database. Assert `is_banned` flag value and that `banned_at` is a recent UTC datetime (ban) or `None` (unban). Also test edge case: `set_banned()` with non-existent UUID returns `None`.

**AC1.3/AC1.4 detail:** Unit tests mock `_update_stytch_metadata` and assert it receives `{"banned": "true"}` (ban) or `{"banned": ""}` (unban). Tests exercise `_cmd_ban()` and `_cmd_unban()` async handlers directly.

**AC1.5 detail:** Unit test via CliRunner: `runner.invoke(app, ["admin", "ban", "nonexistent@email"])` returns non-zero exit code. Mock DB returns no user. Assert no Stytch calls made, no `set_banned()` call made.

### AC2: Real-time client disconnection

| Criterion | Description | Test Type | Test File |
|-----------|-------------|-----------|-----------|
| AC2.1 | Client registry tracks `user_id -> client` mapping on page load | Unit | `tests/unit/test_client_registry.py` |
| AC2.2 | Client registry removes mapping on `client.on_delete` | Unit | `tests/unit/test_client_registry.py` |
| AC2.3 | `disconnect_user()` redirects all user clients to `/banned` | Unit | `tests/unit/test_client_registry.py` |
| AC2.4 | CLI ban triggers kick endpoint, which calls `disconnect_user()` | Unit | `tests/unit/test_kick_endpoint.py` |

**AC2.1 detail:** Call `register(user_id, mock_client)`. Assert the user appears in the internal registry with the correct client. Test multiple clients per user.

**AC2.2 detail:** Call `register()` then `deregister()`. Assert user entry removed when last client deregistered. Assert stale deregister (client not in registry) does not raise.

**AC2.3 detail:** Register multiple mock clients. Call `disconnect_user(user_id)`. Assert `run_javascript('window.location.href = "/banned"', timeout=2.0)` called on each client. Also test stale client edge case: one mock raises exception from `run_javascript`, verify remaining clients still get the call, return count reflects only successes, no exception propagates.

**AC2.4 detail:** POST to `/api/admin/kick` with valid bearer token and a banned user's UUID. Mock `is_user_banned()` to return `True`, mock `disconnect_user()`. Assert `disconnect_user()` called with correct user_id. Assert response contains `{"kicked": <count>, "was_banned": true}`.

### AC3: Banned user rejected on re-auth

| Criterion | Description | Test Type | Test File |
|-----------|-------------|-----------|-----------|
| AC3.1 | Banned user attempting session validation is redirected to `/banned` | E2E | `tests/e2e/test_ban_redirect.py` |
| AC3.2 | `/banned` page displays suspension message with no navigation | E2E | `tests/e2e/test_banned_page.py` |

**AC3.1 detail:** Playwright test: log in as test user, ban them via direct `set_banned()` DB call, navigate to a `page_route`-protected page, assert URL ends with `/banned`.

**AC3.2 detail:** Playwright test: navigate directly to `/banned`. Assert page contains "Your account has been suspended. Contact your instructor." Assert no navigation elements (no sidebar, no header links).

### AC4: Stytch session revocation

| Criterion | Description | Test Type | Test File |
|-----------|-------------|-----------|-----------|
| AC4.1 | `admin ban <email>` revokes all active Stytch sessions | Unit | `tests/unit/test_ban_commands.py` |
| AC4.2 | Ban with user missing `stytch_member_id` warns but continues | Unit | `tests/unit/test_ban_commands.py` |

**AC4.1 detail:** Mock `revoke_member_sessions`. Call `_cmd_ban()`. Assert `revoke_member_sessions(member_id=stytch_member_id)` called exactly once.

**AC4.2 detail:** Set up user with `stytch_member_id=None`. Call `_cmd_ban()`. Assert warning logged/printed. Assert `set_banned()` still called (local ban applied). Assert `revoke_member_sessions` NOT called.

### AC5: List banned users

| Criterion | Description | Test Type | Test File |
|-----------|-------------|-----------|-----------|
| AC5.1 | `admin ban --list` shows banned users with email, name, `banned_at` | Integration | `tests/integration/test_user_ban.py` |
| AC5.2 | `admin ban --list` with no banned users shows empty message | Integration | `tests/integration/test_user_ban.py` |
| AC5.3 | Unbanned user no longer appears in `--list` output | Integration | `tests/integration/test_ban_lifecycle.py` |

**AC5.1 detail:** Create user, ban via `set_banned()`, call `get_banned_users()`. Assert returned list contains user with correct email, display_name, and non-null `banned_at`.

**AC5.2 detail:** Call `get_banned_users()` with no banned users in DB. Assert empty list returned.

**AC5.3 detail:** Full lifecycle integration test: create user, ban, assert in `get_banned_users()`, unban, assert NOT in `get_banned_users()`. Also covers CLI layer via `_cmd_list_banned()` output assertion.

### AC6: Kick endpoint security

| Criterion | Description | Test Type | Test File |
|-----------|-------------|-----------|-----------|
| AC6.1 | Request without `Authorization` header returns 403 | Unit | `tests/unit/test_kick_endpoint.py` |
| AC6.2 | Request with incorrect bearer token returns 403 | Unit | `tests/unit/test_kick_endpoint.py` |
| AC6.3 | Request with valid bearer token triggers ban check and disconnect | Unit | `tests/unit/test_kick_endpoint.py` |

**AC6.1 detail:** POST to `/api/admin/kick` with no `Authorization` header. Assert 403 response. Assert `disconnect_user()` NOT called. Additional edge case: unconfigured `ADMIN_API_SECRET` returns 503 (fail-closed).

**AC6.2 detail:** POST with `Authorization: Bearer wrong-token`. Assert 403 response. Assert `disconnect_user()` NOT called.

**AC6.3 detail:** POST with correct bearer token. Mock `is_user_banned()` returning `True`. Assert 200 response. Assert `disconnect_user()` called with correct user_id.

---

## Human Verification

| Criterion | Description | Why Not Automated | Verification Approach |
|-----------|-------------|-------------------|----------------------|
| AC4.3 | After ban, user cannot obtain a new Stytch session | Requires live Stytch B2B environment; mock auth client cannot verify that Stytch's server-side enforcement actually blocks re-auth based on `trusted_metadata.banned` + session revocation. The unit test verifies our code calls the right APIs, but not that Stytch honours the combination. | **UAT:** Ban a seeded test user via CLI. Attempt to log in via magic link in a browser. Verify Stytch rejects the session or the `page_route` ban check catches the user on first page load. Confirm the user lands on `/banned` and cannot navigate away. |

**Justification for AC4.3 as human verification:** The automated tests (AC4.1, AC4.2) verify that the CLI calls `revoke_member_sessions()` and sets `trusted_metadata.banned`. But whether Stytch's server actually prevents re-authentication when `trusted_metadata.banned = "true"` is a third-party integration behaviour that cannot be validated without a live Stytch environment and a real login flow. The E2E tests use `MockAuthClient`, which simulates but does not prove Stytch behaviour.

---

## Test File Summary

| Test File | Type | Lane | Criteria Covered |
|-----------|------|------|------------------|
| `tests/integration/test_user_ban.py` | Integration | integration (xdist) | AC1.1, AC1.2, AC5.1, AC5.2 |
| `tests/integration/test_ban_lifecycle.py` | Integration | integration (xdist) | AC4.3 (partial), AC5.3 |
| `tests/unit/test_client_registry.py` | Unit | unit (xdist) | AC2.1, AC2.2, AC2.3 |
| `tests/unit/test_kick_endpoint.py` | Unit | unit (xdist) | AC2.4, AC6.1, AC6.2, AC6.3 |
| `tests/unit/test_ban_commands.py` | Unit | unit (xdist) | AC1.3, AC1.4, AC1.5, AC4.1, AC4.2 |
| `tests/e2e/test_banned_page.py` | E2E | playwright | AC3.2 |
| `tests/e2e/test_ban_redirect.py` | E2E | playwright | AC3.1 |

---

## Coverage Matrix

| Criterion | Phase | Automated | Human | File(s) |
|-----------|-------|-----------|-------|---------|
| AC1.1 | 1 | Yes | -- | `test_user_ban.py` |
| AC1.2 | 1 | Yes | -- | `test_user_ban.py` |
| AC1.3 | 5 | Yes | -- | `test_ban_commands.py` |
| AC1.4 | 5 | Yes | -- | `test_ban_commands.py` |
| AC1.5 | 5 | Yes | -- | `test_ban_commands.py` |
| AC2.1 | 3 | Yes | -- | `test_client_registry.py` |
| AC2.2 | 3 | Yes | -- | `test_client_registry.py` |
| AC2.3 | 3 | Yes | -- | `test_client_registry.py` |
| AC2.4 | 4 | Yes | -- | `test_kick_endpoint.py` |
| AC3.1 | 2 | Yes | -- | `test_ban_redirect.py` |
| AC3.2 | 2 | Yes | -- | `test_banned_page.py` |
| AC4.1 | 5 | Yes | -- | `test_ban_commands.py` |
| AC4.2 | 5 | Yes | -- | `test_ban_commands.py` |
| AC4.3 | 5 | -- | Yes | UAT: live Stytch login attempt |
| AC5.1 | 1 | Yes | -- | `test_user_ban.py` |
| AC5.2 | 1 | Yes | -- | `test_user_ban.py` |
| AC5.3 | 5 | Yes | -- | `test_ban_lifecycle.py` |
| AC6.1 | 4 | Yes | -- | `test_kick_endpoint.py` |
| AC6.2 | 4 | Yes | -- | `test_kick_endpoint.py` |
| AC6.3 | 4 | Yes | -- | `test_kick_endpoint.py` |

**Totals:** 19 criteria automated, 1 criterion human-verified (AC4.3).
