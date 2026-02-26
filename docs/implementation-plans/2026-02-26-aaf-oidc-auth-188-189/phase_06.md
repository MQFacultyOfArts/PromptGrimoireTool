# AAF OIDC Authentication — Phase 6: B2C Fallback Documentation

**Goal:** Document the migration path to Stytch B2C if B2B SSO proves unworkable

**Architecture:** Write a developer-actionable migration guide covering what changes, what stays, what's lost, what's gained, and estimated effort. Based on concrete codebase investigation of B2B surface area.

**Tech Stack:** Markdown documentation

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-02-26

---

## Acceptance Criteria Coverage

This phase implements:

### aaf-oidc-auth-188-189.AC5: B2C fallback documented
- **aaf-oidc-auth-188-189.AC5.1 Success:** `docs/b2c-fallback.md` exists with migration guide
- **aaf-oidc-auth-188-189.AC5.2 Success:** Document covers: what changes, what stays, what's lost, what's gained, estimated effort

---

<!-- START_TASK_1 -->
### Task 1: Write B2C fallback migration guide

**Verifies:** aaf-oidc-auth-188-189.AC5.1, aaf-oidc-auth-188-189.AC5.2

**Files:**
- Create: `docs/b2c-fallback.md`

**Implementation:**

Create `docs/b2c-fallback.md` with the following structure and content. The document must be a complete migration guide that a developer can follow without additional context.

**Document outline:**

```markdown
# Stytch B2C Fallback Migration Guide

## When to Use This Guide

This guide applies if the Stytch B2B OIDC connection with AAF proves unworkable
(fundamental incompatibility, not configuration error). Migrate only if Phase 1
diagnostic confirms Stytch's generic OIDC handler cannot work with AAF.

## What Changes

### Import and Client
- `from stytch import B2BClient` → `from stytch import Client`
- `StytchB2BClient` class renamed, constructor simplified
- File: `src/promptgrimoire/auth/client.py` (1 import, 1 class)

### Remove `organization_id`
- Remove from `StytchConfig.default_org_id` (`config.py:43`)
- Remove from protocol: `send_magic_link()`, `get_oauth_start_url()` params (`protocol.py`)
- Remove from models: `AuthResult.organization_id`, `SessionResult.organization_id` (`models.py`)
- Remove from client: 6 references in `client.py`
- Remove from mock: 7 references including `MOCK_ORG_ID` (`mock.py`)
- Remove from pages: validation checks and session storage (`pages/auth.py`)
- Remove env var: `STYTCH__DEFAULT_ORG_ID`

### Remove SSO (custom OIDC)
B2C does not support custom OIDC connections. Remove entirely:
- Protocol methods: `authenticate_sso()`, `get_sso_start_url()` (`protocol.py`)
- Client methods: `authenticate_sso()`, `get_sso_start_url()` (`client.py:163-267`)
- Mock methods: `authenticate_sso()`, `get_sso_start_url()` (`mock.py`)
- SSO callback: `/auth/sso/callback` route (`pages/auth.py:473-522`)
- SSO button: `_build_sso_section()` (`pages/auth.py:276-317`)
- Config: `sso_connection_id`, `sso_requires_public_token` validator (`config.py:44-51`)
- Remove env vars: `STYTCH__SSO_CONNECTION_ID`, `STYTCH__PUBLIC_TOKEN`

### Update API calls
- Magic links: `client.magic_links.email.login_or_signup_async(organization_id=..., ...)` →
  `client.magic_links.email.login_or_create_async(email=...)`
- OAuth: `client.oauth.authenticate_async(...)` → same name, different response shape
- Sessions: `client.sessions.authenticate_async(...)` → same name, response has `user` not `member`

### Update tests
- ~20+ tests reference `organization_id` — remove assertions
- SSO tests removed entirely
- Mock constants: remove `MOCK_ORG_ID`
- E2E tests: remove SSO flow test, update OAuth tests

## What Stays

- All business logic (database, ACLs, workspaces, annotations)
- User model and database schema (unaffected)
- `is_privileged_user()` and `check_workspace_access()` (role-based, not org-based)
- Magic link authentication flow (API changes, but logic identical)
- GitHub OAuth authentication flow (minor API changes)
- Google OAuth authentication flow (B2C supports Google natively)
- Session management pattern (token + JWT, same concepts)
- Factory pattern (`get_auth_client()`)
- Mock client pattern (same interface, reduced surface)
- `derive_roles_from_metadata()` — if metadata still available via OAuth

## What's Lost

- **AAF OIDC login** — B2C cannot connect to custom OIDC providers. MQ staff
  would need to use Google or magic link instead of institutional SSO.
- **Organisation-scoped auth** — no multi-tenant org concept
- **JIT provisioning via SSO** — must use email domain JIT or manual invitation
- **eduperson_affiliation mapping** — AAF attributes no longer available without
  custom OIDC. Role derivation from `trusted_metadata` becomes dead code.
- **SAML support** — if ever needed in future, not available in B2C

## What's Gained

- **Simpler API** — no `organization_id` parameter on any call
- **No org bootstrapping** — no need to create/manage Stytch organisation
- **Google One-Tap** — seamless one-click sign-in for Google users
- **Account deduplication** — email + OAuth auto-link
- **Fewer config vars** — remove `STYTCH__DEFAULT_ORG_ID`, `STYTCH__SSO_CONNECTION_ID`

## Estimated Effort

| Area | Files | Lines changed (est.) |
|------|-------|---------------------|
| Auth client | 1 | ~30 (rewrite SDK calls) |
| Auth protocol | 1 | ~20 (remove SSO, remove org_id) |
| Auth models | 1 | ~5 (remove org_id fields) |
| Auth mock | 1 | ~30 (remove SSO, remove org refs) |
| Auth factory | 1 | ~5 (import change) |
| Config | 1 | ~10 (remove SSO + org config) |
| Pages/auth | 1 | ~50 (remove SSO UI + callback, remove org checks) |
| Tests | 3-5 | ~60 (remove SSO tests, update assertions) |
| **Total** | **~10 files** | **~210 lines** |

**Estimated time:** 4-8 hours for an engineer familiar with the codebase.
2-4 hours if the auth client changes are mechanical (import swap + param removal).

## Migration Checklist

1. [ ] Create new Stytch B2C project in dashboard
2. [ ] Enable Google OAuth in B2C dashboard
3. [ ] Update `src/promptgrimoire/auth/client.py` — swap B2BClient → Client
4. [ ] Update `src/promptgrimoire/auth/protocol.py` — remove SSO methods, remove org_id params
5. [ ] Update `src/promptgrimoire/auth/models.py` — remove organization_id fields
6. [ ] Update `src/promptgrimoire/auth/mock.py` — remove SSO, remove org references
7. [ ] Update `src/promptgrimoire/auth/factory.py` — import change
8. [ ] Update `src/promptgrimoire/config.py` — remove SSO + org config
9. [ ] Update `src/promptgrimoire/pages/auth.py` — remove SSO UI, remove org validation
10. [ ] Update tests — remove SSO tests, update org_id assertions
11. [ ] Remove env vars: STYTCH__DEFAULT_ORG_ID, STYTCH__SSO_CONNECTION_ID, STYTCH__PUBLIC_TOKEN
12. [ ] Run `uv run test-all` — verify all tests pass
13. [ ] Manual test: magic link + Google OAuth work end-to-end
```

**Verification:**

Verify the file exists and is readable:
```bash
ls -la docs/b2c-fallback.md
```

**Commit:** `docs: add B2C fallback migration guide`

<!-- END_TASK_1 -->

---

## Phase Completion Criteria

Phase 6 is complete when:
1. `docs/b2c-fallback.md` exists with complete migration guide (Task 1)
2. Document covers: what changes, what stays, what's lost, what's gained, estimated effort (AC5.2)
3. `uv run test-all` passes with zero failures (no code changes, so should be trivially true)
