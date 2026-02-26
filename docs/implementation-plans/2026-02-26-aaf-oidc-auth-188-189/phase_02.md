# AAF OIDC Authentication — Phase 2: Trusted Metadata Pipeline

**Goal:** Extend the auth flow to read AAF attributes from Stytch SSO responses and map them to app roles

**Architecture:** Add `trusted_metadata` field to AuthResult, pass it through from Stytch SSO response, create `derive_roles_from_metadata()` pure function to map `eduperson_affiliation` to app roles, merge derived roles in SSO callback

**Tech Stack:** Python 3.14, Stytch B2B SDK, pytest

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-02-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### aaf-oidc-auth-188-189.AC4: AAF attributes mapped to app roles
- **aaf-oidc-auth-188-189.AC4.1 Success:** AAF user with `eduperson_affiliation` containing "staff" gets `instructor` role and passes `is_privileged_user()` check
- **aaf-oidc-auth-188-189.AC4.2 Success:** AAF user with `eduperson_affiliation` containing "faculty" gets `instructor` role
- **aaf-oidc-auth-188-189.AC4.3 Success:** AAF user with `eduperson_affiliation` containing "student" gets no special roles, fails `is_privileged_user()` check
- **aaf-oidc-auth-188-189.AC4.4 Edge:** AAF user with missing `eduperson_affiliation` (attribute not released by institution) gets no special roles (fail-open to unprivileged)
- **aaf-oidc-auth-188-189.AC4.5 Edge:** AAF user with multiple affiliations (e.g. "staff" and "student") gets `instructor` role (highest privilege wins)
- **aaf-oidc-auth-188-189.AC4.6 Success:** `trusted_metadata` from Stytch response is read and passed through in `AuthResult`

### aaf-oidc-auth-188-189.AC1: AAF OIDC login works end-to-end
- **aaf-oidc-auth-188-189.AC1.2 Success:** Returning AAF user logs in again; existing local user record is updated (last_login), not duplicated
- **aaf-oidc-auth-188-189.AC1.4 Failure:** Invalid/expired SSO token returns error, does not create session

### aaf-oidc-auth-188-189.AC3: JIT provisioning
- **aaf-oidc-auth-188-189.AC3.1 Success:** First-time AAF user auto-creates local account without pre-invitation (integration test via `_upsert_local_user()`)

---

## Key Files Reference

For task-implementor context:

| File | Role |
|------|------|
| `src/promptgrimoire/auth/models.py` | AuthResult dataclass (frozen) — add `trusted_metadata` field |
| `src/promptgrimoire/auth/client.py:163-202` | StytchB2BClient.authenticate_sso() — pass through `response.member.trusted_metadata` |
| `src/promptgrimoire/auth/__init__.py` | Add `derive_roles_from_metadata()` alongside `is_privileged_user()` |
| `src/promptgrimoire/auth/mock.py:159-182` | MockAuthClient.authenticate_sso() — return sample `trusted_metadata` |
| `src/promptgrimoire/pages/auth.py:473-522` | SSO callback — call `derive_roles_from_metadata()`, merge roles |
| `tests/unit/test_auth_roles.py` | Add tests for `derive_roles_from_metadata()` |
| `tests/unit/test_auth_client.py:224-280` | Add test for `trusted_metadata` passthrough |
| `tests/unit/test_mock_client.py:130-145` | Add test for mock `trusted_metadata` |
| `CLAUDE.md` | Project conventions and test commands |
| `docs/testing.md` | Test patterns, async fixture rule, DB isolation |

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add `trusted_metadata` field to AuthResult

**Verifies:** aaf-oidc-auth-188-189.AC4.6

**Files:**
- Modify: `src/promptgrimoire/auth/models.py` — add field to AuthResult dataclass
- Test: `tests/unit/test_auth_client.py` — verify existing tests still pass (no new test needed for the field itself — type checker validates it)

**Implementation:**

In `src/promptgrimoire/auth/models.py`:

1. Add `from typing import Any` import (if not already present)
2. Add field to `AuthResult` after `roles`:
   ```python
   trusted_metadata: dict[str, Any] | None = None
   ```

This is backwards-compatible — all existing AuthResult constructors use keyword arguments and the new field has a default.

**Verification:**

```bash
uv run test-all
```

Expected: All existing tests pass unchanged (the new field has a default value).

**Commit:** `feat(auth): add trusted_metadata field to AuthResult`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `derive_roles_from_metadata()` function

**Verifies:** aaf-oidc-auth-188-189.AC4.1, aaf-oidc-auth-188-189.AC4.2, aaf-oidc-auth-188-189.AC4.3, aaf-oidc-auth-188-189.AC4.4, aaf-oidc-auth-188-189.AC4.5

**Files:**
- Modify: `src/promptgrimoire/auth/__init__.py` — add function and constant
- Test: `tests/unit/test_auth_roles.py` (unit)

**Implementation:**

In `src/promptgrimoire/auth/__init__.py`:

1. Add `from typing import Any` import
2. Add constant (near existing `_PRIVILEGED_ROLES`):
   ```python
   _STAFF_AFFILIATIONS: frozenset[str] = frozenset({"staff", "faculty"})
   ```
3. Add function:
   ```python
   def derive_roles_from_metadata(
       trusted_metadata: dict[str, Any] | None,
   ) -> list[str]:
       """Map IdP attributes to app roles.

       Reads eduperson_affiliation from trusted_metadata.
       AAF sends affiliations as semicolon-delimited string (e.g. "staff;faculty").
       staff/faculty → ["instructor"]. Otherwise → [].
       """
       if not trusted_metadata:
           return []
       affiliation_raw = trusted_metadata.get("eduperson_affiliation")
       if not affiliation_raw:
           return []
       # AAF typically sends semicolon-delimited string, but some IdPs may send a list
       if isinstance(affiliation_raw, list):
           affiliations = {a.strip().lower() for a in affiliation_raw if isinstance(a, str)}
       elif isinstance(affiliation_raw, str):
           affiliations = {a.strip().lower() for a in affiliation_raw.split(";")}
       else:
           return []
       if affiliations & _STAFF_AFFILIATIONS:
           return ["instructor"]
       return []
   ```
4. Add `derive_roles_from_metadata` to `__all__`

**Testing:**

Tests in `tests/unit/test_auth_roles.py` must verify each AC listed above:

- aaf-oidc-auth-188-189.AC4.1: Input `{"eduperson_affiliation": "staff"}` → `["instructor"]`, and `is_privileged_user({"is_admin": False, "roles": ["instructor"]})` returns True
- aaf-oidc-auth-188-189.AC4.2: Input `{"eduperson_affiliation": "faculty"}` → `["instructor"]`
- aaf-oidc-auth-188-189.AC4.3: Input `{"eduperson_affiliation": "student"}` → `[]`, and `is_privileged_user({"is_admin": False, "roles": []})` returns False
- aaf-oidc-auth-188-189.AC4.4: Input `None` → `[]`; Input `{}` → `[]`; Input `{"eduperson_affiliation": ""}` → `[]`
- aaf-oidc-auth-188-189.AC4.5: Input `{"eduperson_affiliation": "staff;student"}` → `["instructor"]` (highest privilege wins)

Additional edge cases to test:
- `{"eduperson_affiliation": "faculty;staff"}` → `["instructor"]` (no duplicates)
- `{"eduperson_affiliation": "  Staff  "}` → `["instructor"]` (case-insensitive, whitespace-tolerant)
- `{"eduperson_affiliation": ["staff", "student"]}` → `["instructor"]` (list-type input from non-standard IdPs)
- `{"eduperson_affiliation": 42}` → `[]` (non-string, non-list type returns empty)

**Verification:**

```bash
uv run pytest tests/unit/test_auth_roles.py -v
```

Expected: All new tests pass.

**Commit:** `feat(auth): add derive_roles_from_metadata for AAF affiliation mapping`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Pass `trusted_metadata` through StytchB2BClient and MockAuthClient

**Verifies:** aaf-oidc-auth-188-189.AC4.6

**Files:**
- Modify: `src/promptgrimoire/auth/client.py:163-202` — read `response.member.trusted_metadata`
- Modify: `src/promptgrimoire/auth/mock.py:159-182` — return sample `trusted_metadata`
- Test: `tests/unit/test_auth_client.py` — verify trusted_metadata passthrough (unit)
- Test: `tests/unit/test_mock_client.py` — verify mock returns trusted_metadata (unit)

**Implementation:**

In `src/promptgrimoire/auth/client.py`, in the `authenticate_sso()` success path (around line 185-193), add `trusted_metadata` to the AuthResult constructor:
```python
return AuthResult(
    success=True,
    session_token=response.session_token,
    session_jwt=response.session_jwt,
    member_id=response.member_id,
    organization_id=response.organization_id,
    email=response.member.email_address,
    name=getattr(response.member, "name", None),
    roles=roles,
    trusted_metadata=getattr(response.member, "trusted_metadata", None),
)
```

In `src/promptgrimoire/auth/mock.py`, in `authenticate_sso()` success return (around line 169-178), add `trusted_metadata`:
```python
return AuthResult(
    success=True,
    session_token=MOCK_VALID_SESSION,
    session_jwt="mock-sso-jwt",
    member_id=MOCK_MEMBER_ID,
    organization_id=MOCK_ORG_ID,
    email="aaf-user@uni.edu",
    name="SSO User",
    roles=["stytch_member", "instructor"],
    trusted_metadata={
        "eduperson_affiliation": "staff",
        "schac_home_organization": "uni.edu",
    },
)
```

**Testing:**

In `tests/unit/test_auth_client.py` TestAuthenticateSSO:
- aaf-oidc-auth-188-189.AC4.6: Add `mock_member.trusted_metadata = {"eduperson_affiliation": "staff"}` to the mock setup, then assert `result.trusted_metadata == {"eduperson_affiliation": "staff"}`
- aaf-oidc-auth-188-189.AC1.4: Add test that calls `authenticate_sso(token="invalid-token")` with the Stytch mock raising an exception, then assert `result.success is False` and `result.session_token is None` (verifies the existing error-handling branch)

In `tests/unit/test_mock_client.py`:
- Verify mock SSO returns `trusted_metadata` containing `eduperson_affiliation` and `schac_home_organization`

**Verification:**

```bash
uv run pytest tests/unit/test_auth_client.py::TestAuthenticateSSO -v
uv run pytest tests/unit/test_mock_client.py -v
```

Expected: All tests pass including new assertions.

**Commit:** `feat(auth): pass trusted_metadata through SSO authentication`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Merge derived roles in SSO callback

**Verifies:** aaf-oidc-auth-188-189.AC4.1, aaf-oidc-auth-188-189.AC1.2, aaf-oidc-auth-188-189.AC3.1

**Files:**
- Modify: `src/promptgrimoire/pages/auth.py:495-515` — add role derivation and merge in SSO callback
- Test: `tests/integration/test_auth_upsert.py` — verify first-time provisioning and no-duplicate upsert

**Implementation:**

In `src/promptgrimoire/pages/auth.py`, in the `sso_callback()` function, after `result = await auth_client.authenticate_sso(token=token)` and inside the `if result.success:` block, before calling `_upsert_local_user()`:

1. Add import at top of file: `from promptgrimoire.auth import derive_roles_from_metadata`
2. Add role derivation:
   ```python
   if result.success:
       # Derive app roles from AAF metadata and merge with Stytch roles
       derived_roles = derive_roles_from_metadata(result.trusted_metadata)
       all_roles = list(dict.fromkeys([*result.roles, *derived_roles]))  # Deduplicate, preserve order

       # Upsert user in local database
       user_id, is_admin = await _upsert_local_user(
           email=result.email or "",
           stytch_member_id=result.member_id or "",
           display_name=result.name,
           roles=all_roles,
       )

       _set_session_user(
           email=result.email or "",
           member_id=result.member_id or "",
           organization_id=result.organization_id or "",
           session_token=result.session_token or "",
           roles=all_roles,
           name=result.name,
           auth_method="sso_aaf",
           user_id=user_id,
           is_admin=is_admin,
       )
       ui.navigate.to("/")
   ```

Note: `dict.fromkeys()` deduplicates while preserving insertion order — if Stytch already assigns "instructor" via RBAC AND metadata derivation also produces "instructor", the role appears only once.

**Testing:**

In `tests/integration/test_auth_upsert.py` (new file):
- aaf-oidc-auth-188-189.AC3.1: Call `_upsert_local_user(email="new-aaf@mq.edu.au", stytch_member_id="member-new", display_name="New AAF User", roles=["instructor"])` for a user that does not exist in the database. Assert a new user record is created (returns a valid `user_id`) and the user has the expected roles. This verifies first-time AAF users auto-create local accounts.
- aaf-oidc-auth-188-189.AC1.2: Call `_upsert_local_user()` with the same `stytch_member_id` a second time. Assert user count with that `stytch_member_id` is 1 (not 2). Assert `last_login` on the second call is later than the first.

This requires database access — use the `db_session` async fixture from `tests/conftest.py`.

**Verification:**

```bash
uv run pytest tests/integration/test_auth_upsert.py -v
uv run test-all
```

Expected: All tests pass. The upsert integration test confirms returning users are updated, not duplicated.

**UAT:** After implementation, manually verify SSO login:
1. Log in via AAF SSO with test user
2. Confirm session is active and user record exists in database
3. Log out, log in again with same user
4. Confirm only one user record exists (not duplicated)

**Commit:** `feat(auth): merge AAF-derived roles in SSO callback`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Configure Stytch OIDC attribute mapping (dashboard)

**Verifies:** aaf-oidc-auth-188-189.AC4.6

**This is a manual/infrastructure task. No code changes.**

In the Stytch B2B dashboard, configure the OIDC connection's attribute mapping:

1. Navigate to Authentication > SSO > [OIDC connection]
2. Configure attribute mapping so AAF claims flow to `trusted_metadata`:
   - Map `eduperson_affiliation` → `trusted_metadata.eduperson_affiliation`
   - Map `schac_home_organization` → `trusted_metadata.schac_home_organization`
3. Verify custom scopes include: `openid profile email eduperson_affiliation schac_home_organization`

**Verification:**

Log in with AAF test user. After authentication, check app logs for the SSO callback — `result.trusted_metadata` should contain `eduperson_affiliation` from the AAF user.

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

---

## Phase Completion Criteria

Phase 2 is complete when:
1. `AuthResult` has `trusted_metadata` field (Task 1)
2. `derive_roles_from_metadata()` passes all AC4 tests (Task 2)
3. `StytchB2BClient` and `MockAuthClient` pass through `trusted_metadata` (Task 3)
4. SSO callback merges derived roles with Stytch roles (Task 4)
5. Stytch attribute mapping configured (Task 5)
6. `uv run test-all` passes with zero failures
