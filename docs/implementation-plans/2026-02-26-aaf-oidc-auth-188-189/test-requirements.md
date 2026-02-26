# AAF OIDC Authentication — Test Requirements

Generated from acceptance criteria in `docs/design-plans/2026-02-26-aaf-oidc-auth-188-189.md`.

---

## AC → Phase → Test Traceability

### aaf-oidc-auth-188-189.AC1: AAF OIDC login works end-to-end

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC1.1 | Success | Phase 1 (manual), Phase 5 (manual) | Phase 1 Task 5 Step 1, Phase 5 Task 3 Step 1 | Manual |
| AC1.2 | Success | Phase 2 Task 4, Phase 5 Task 3 | `tests/integration/test_auth_upsert.py` | Automated (integration) + Manual |
| AC1.3 | Failure | Phase 1 (manual) | Phase 1 Task 5 Step 2 | Manual |
| AC1.4 | Failure | Phase 2 Task 3, Phase 5 Task 3 | `tests/unit/test_auth_client.py::TestAuthenticateSSO` | Automated (unit) + Manual |
| AC1.5 | Edge | Phase 1 (manual) | Phase 1 Task 5 Step 3 | Manual |

### aaf-oidc-auth-188-189.AC2: Google OAuth login works end-to-end

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC2.1 | Success | Phase 3 Task 3 (manual) | Phase 3 Task 3 Verification | Manual |
| AC2.2 | Success | Phase 3 Task 1 | Existing E2E test for login page button ordering | E2E |
| AC2.3 | Success | Phase 3 Task 2 | Tests verifying `auth_method="oauth"` | Automated (unit/E2E) |
| AC2.4 | Failure | Phase 3 Task 2 | Existing OAuth error test | Automated (E2E) |

### aaf-oidc-auth-188-189.AC3: JIT provisioning

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC3.1 | Success | Phase 2 Task 4, Phase 5 Task 3 | `tests/integration/test_auth_upsert.py` | Automated (integration) + Manual |
| AC3.2 | Success | Phase 3 Task 3 (manual) | Phase 3 Task 3 Verification | Manual |
| AC3.3 | Edge | Phase 3 Task 3 (manual) | Phase 3 Task 3 Step 3 | Manual |

### aaf-oidc-auth-188-189.AC4: AAF attributes mapped to app roles

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC4.1 | Success | Phase 2 Task 2 | `tests/unit/test_auth_roles.py` | Automated (unit) |
| AC4.2 | Success | Phase 2 Task 2 | `tests/unit/test_auth_roles.py` | Automated (unit) |
| AC4.3 | Success | Phase 2 Task 2 | `tests/unit/test_auth_roles.py` | Automated (unit) |
| AC4.4 | Edge | Phase 2 Task 2 | `tests/unit/test_auth_roles.py` | Automated (unit) |
| AC4.5 | Edge | Phase 2 Task 2 | `tests/unit/test_auth_roles.py` | Automated (unit) |
| AC4.6 | Success | Phase 2 Tasks 1+3 | `tests/unit/test_auth_client.py`, `tests/unit/test_mock_client.py` | Automated (unit) |

### aaf-oidc-auth-188-189.AC5: B2C fallback documented

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC5.1 | Success | Phase 6 Task 1 | `ls -la docs/b2c-fallback.md` | Manual (file exists) |
| AC5.2 | Success | Phase 6 Task 1 | Human review of document content | Manual |

### aaf-oidc-auth-188-189.AC6: AAF test federation established

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC6.1 | Success | Phase 1 Task 1 | AAF test federation manager | Manual (infrastructure) |
| AC6.2 | Success | Phase 1 Task 2 | Rapid IdP dashboard | Manual (infrastructure) |
| AC6.3 | Success | Phase 1 Task 3+5 | Phase 1 Task 5 Step 1 | Manual (infrastructure) |

### aaf-oidc-auth-188-189.AC7: Magic link domain enforcement

| AC | Type | Phase | Test Location | Automation |
|----|------|-------|---------------|------------|
| AC7.1 | Success | Phase 4 Task 1 | `tests/unit/test_magic_link_domain.py` | Automated (unit) |
| AC7.2 | Success | Phase 4 Task 1 | `tests/unit/test_magic_link_domain.py` | Automated (unit) |
| AC7.3 | Failure | Phase 4 Tasks 1+2 | `tests/unit/test_magic_link_domain.py`, `tests/e2e/test_auth_pages.py` | Automated (unit + E2E) |
| AC7.4 | Success | Phase 4 Task 2 | `tests/e2e/test_auth_pages.py` | Automated (E2E) |

---

## New Test Files

| File | Phase | Contents |
|------|-------|----------|
| `tests/unit/test_auth_roles.py` (extend) | Phase 2 | `derive_roles_from_metadata()` — all AC4 criteria |
| `tests/unit/test_auth_client.py` (extend) | Phase 2 | `trusted_metadata` passthrough, invalid token handling |
| `tests/unit/test_mock_client.py` (extend) | Phase 2 | Mock `trusted_metadata` |
| `tests/integration/test_auth_upsert.py` (new) | Phase 2 | First-time provisioning (AC3.1), no-duplicate upsert (AC1.2) |
| `tests/unit/test_magic_link_domain.py` (new) | Phase 4 | Domain validation — all AC7 criteria |
| `tests/e2e/test_auth_pages.py` (modify) | Phase 4 | Update magic link test for domain enforcement |

---

## Coverage Summary

| Category | Automated | Manual | Total |
|----------|-----------|--------|-------|
| AC1 (AAF OIDC) | 2 | 3 | 5 |
| AC2 (Google OAuth) | 3 | 1 | 4 |
| AC3 (JIT) | 1 | 2 | 3 |
| AC4 (Role mapping) | 6 | 0 | 6 |
| AC5 (B2C fallback) | 0 | 2 | 2 |
| AC6 (Test federation) | 0 | 3 | 3 |
| AC7 (Domain enforcement) | 4 | 0 | 4 |
| **Total** | **16** | **11** | **27** |

Manual-only criteria (AC1.1, AC1.3, AC1.5, AC2.1, AC3.2, AC3.3, AC5.1, AC5.2, AC6.1, AC6.2, AC6.3) are infrastructure/dashboard tasks or require real AAF/Google federation interaction that cannot be automated in CI.
