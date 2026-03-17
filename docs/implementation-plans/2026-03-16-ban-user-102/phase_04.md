# Ban User Implementation Plan — Phase 4: Internal Kick Endpoint

**Goal:** HTTP endpoint for CLI to trigger real-time disconnect of banned users, secured by shared secret.

**Architecture:** `POST /api/admin/kick` Starlette route in `__init__.py`, following `/healthz` pattern. Secret validated via `hmac.compare_digest`. Reads ban state from DB (source of truth), calls `disconnect_user()` if banned. `ADMIN_API_SECRET` in `AdminConfig` sub-model with `SecretStr`.

**Tech Stack:** Starlette Route, hmac, pydantic-settings (SecretStr)

**Scope:** Phase 4 of 5 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ban-user-102.AC2: Real-time client disconnection
- **ban-user-102.AC2.4 Success:** CLI ban command triggers kick endpoint, which calls `disconnect_user()` for the banned user

### ban-user-102.AC6: Kick endpoint security
- **ban-user-102.AC6.1 Failure:** Request without `Authorization` header returns 403
- **ban-user-102.AC6.2 Failure:** Request with incorrect bearer token returns 403
- **ban-user-102.AC6.3 Success:** Request with valid bearer token triggers ban check and disconnect

---

<!-- START_TASK_1 -->
### Task 1: Add `AdminConfig` to settings

**Files:**
- Modify: `src/promptgrimoire/config.py` (add `AdminConfig` sub-model)

**Implementation:**

Add a new sub-model following the `AlertingConfig` pattern at `config.py`:

```python
class AdminConfig(BaseModel):
    """Admin API configuration."""

    admin_api_secret: SecretStr = SecretStr("")
```

Register it in the `Settings` class:

```python
admin: AdminConfig = AdminConfig()
```

Environment variable: `ADMIN__ADMIN_API_SECRET=<secret>` (double underscore for nesting).

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All existing tests pass (no regressions).

**Commit:** `feat(config): add AdminConfig with admin_api_secret setting`

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Create `/api/admin/kick` endpoint

**Verifies:** ban-user-102.AC2.4, ban-user-102.AC6.1, ban-user-102.AC6.2, ban-user-102.AC6.3

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (add Starlette route after `/healthz`, around line 306)

**Implementation:**

Follow the `/healthz` pattern at `__init__.py:299-306`. Add a new async handler and route:

```python
async def kick_user(request: Request) -> JSONResponse:
    ...
```

The handler should:

1. **Check secret is configured:** Read `get_settings().admin.admin_api_secret`. If empty string, return `JSONResponse({"error": "ADMIN_API_SECRET not configured"}, status_code=503)`.

2. **Validate Authorization header:** Extract `Authorization` header, expect `Bearer <token>`. Use `hmac.compare_digest(token, secret.get_secret_value())` for timing-safe comparison. Return `JSONResponse({"error": "Forbidden"}, status_code=403)` on failure.

3. **Parse request body:** Read JSON body, extract `user_id` (UUID string). Return 400 if missing or invalid UUID.

4. **Check ban state in DB:** Call `is_user_banned(user_id)` from `db/users.py` (created in Phase 1). This is the source of truth — don't trust request body for ban state.

5. **Kick if banned:** If `is_banned`, call `disconnect_user(user_id)` and return `JSONResponse({"kicked": count, "was_banned": True})`. If not banned, return `JSONResponse({"kicked": 0, "was_banned": False})`.

Register the route:
```python
app.routes.insert(0, Route("/api/admin/kick", kick_user, methods=["POST"]))
```

Import `from starlette.requests import Request` and `from starlette.responses import JSONResponse`.
Import `hmac` from stdlib.
Import `disconnect_user` from `auth.client_registry` and the DB function to check ban state.

**Testing:**

Tests must verify each AC listed above:
- ban-user-102.AC6.1: POST without Authorization header returns 403
- ban-user-102.AC6.2: POST with wrong bearer token returns 403
- ban-user-102.AC6.3: POST with valid bearer token returns 200 and triggers disconnect
- ban-user-102.AC2.4: Valid request with a banned user calls disconnect_user and returns kicked count

These should be unit tests that mock the DB function and `disconnect_user()`. Use `httpx.AsyncClient` with the Starlette app to make requests. Place in `tests/unit/test_kick_endpoint.py`.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Complexipy check:**

```bash
uv run complexipy src/promptgrimoire/__init__.py
```

**Commit:** `feat(api): add POST /api/admin/kick endpoint with secret validation`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify kick endpoint with unconfigured secret

**Verifies:** ban-user-102.AC6.1 (edge case: secret not configured returns 503, not 403)

**Files:**
- Modify: `tests/unit/test_kick_endpoint.py` (add test case)

**Testing:**

Add a test that calls the endpoint when `ADMIN_API_SECRET` is empty (default). Verify:
- Returns 503 (not 403) with error message "ADMIN_API_SECRET not configured"
- Does not attempt to validate the Authorization header
- Does not call disconnect_user()

This verifies the "fail closed" behaviour specified in the design plan.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `test(api): verify kick endpoint fails closed without configured secret`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. Set `ADMIN__ADMIN_API_SECRET=test-secret-123` in `.env`
2. Start the app: `uv run run.py`
3. Test forbidden: `curl -X POST http://localhost:8080/api/admin/kick -d '{"user_id":"any"}' -H 'Content-Type: application/json'` — expect 403
4. Test wrong token: `curl -X POST http://localhost:8080/api/admin/kick -d '{"user_id":"any"}' -H 'Authorization: Bearer wrong' -H 'Content-Type: application/json'` — expect 403
5. Test valid token (unbanned user): `curl -X POST http://localhost:8080/api/admin/kick -d '{"user_id":"<real-uuid>"}' -H 'Authorization: Bearer test-secret-123' -H 'Content-Type: application/json'` — expect `{"kicked": 0, "was_banned": false}`

## Evidence Required
- [ ] Test output showing green for all kick endpoint tests
- [ ] curl output showing 403 for invalid/missing tokens
