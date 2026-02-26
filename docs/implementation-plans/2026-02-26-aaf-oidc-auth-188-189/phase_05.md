# AAF OIDC Authentication — Phase 5: Production AAF Cutover

**Goal:** Switch from AAF test federation to production AAF credentials

**Architecture:** No code changes. Update Stytch OIDC connection issuer and credentials from test to production. Update environment config if connection ID changed.

**Tech Stack:** Stytch B2B dashboard, AAF Federation Manager (production)

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-02-26

---

## Acceptance Criteria Coverage

This phase verifies (manually):

### aaf-oidc-auth-188-189.AC1: AAF OIDC login works end-to-end
- **aaf-oidc-auth-188-189.AC1.1 Success:** MQ staff user clicks "Login with AAF", authenticates at AAF, returns to app with active session and local user record created
- **aaf-oidc-auth-188-189.AC1.2 Success:** Returning AAF user logs in again; existing local user record is updated (last_login), not duplicated
- **aaf-oidc-auth-188-189.AC1.4 Failure:** Invalid/expired SSO token returns error, does not create session

### aaf-oidc-auth-188-189.AC3: JIT provisioning
- **aaf-oidc-auth-188-189.AC3.1 Success:** First-time AAF user auto-creates local account without pre-invitation

---

<!-- START_TASK_1 -->
### Task 1: Register production AAF OIDC client

**Verifies:** None (infrastructure setup)

**This is a manual/infrastructure task. No code changes.**

**Step 1: Register OIDC client at AAF production federation**

1. Go to `https://manager.aaf.edu.au/oidc/clients/new`
2. Authenticate with AAF production credentials
3. Register a new OIDC Relying Party with:
   - **Client name:** PromptGrimoire
   - **Redirect URI:** Copy from Stytch OIDC connection `redirect_url` (same format as test: `https://api.stytch.com/v1/b2b/sso/callback/{connection-id}`)
   - **Grant type:** Authorization Code
4. Record `client_id` and `client_secret` immediately — secret cannot be recovered
5. Store securely (not in code)

**Important:** AAF production registrations take **~2 hours** to propagate. Plan accordingly — register well before testing.

**Verification:**
- Client appears in AAF production federation manager
- Credentials recorded securely

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update Stytch OIDC connection for production

**Verifies:** None (infrastructure setup)

**This is a manual/infrastructure task. No code changes.**

**Step 1: Update Stytch OIDC connection**

In the Stytch B2B dashboard:

| Field | Test value (replace) | Production value |
|-------|---------------------|-----------------|
| `issuer` | `https://central.test.aaf.edu.au` | `https://central.aaf.edu.au` |
| `client_id` | Test client ID | Production client ID (from Task 1) |
| `client_secret` | Test client secret | Production client secret (from Task 1) |

All other fields (attribute mapping, custom scopes) remain unchanged — they're identical between test and production.

**Step 2: Update environment config (if needed)**

If the Stytch OIDC connection was recreated (new `connection_id`), update `.env`:
```
STYTCH__SSO_CONNECTION_ID=<new-connection-id>
```

If the connection was updated in-place, no env change needed.

**Verification:**
- Stytch OIDC connection shows production issuer
- Connection status is "Active"

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: End-to-end production verification

**Verifies:** aaf-oidc-auth-188-189.AC1.1, aaf-oidc-auth-188-189.AC1.2, aaf-oidc-auth-188-189.AC1.4, aaf-oidc-auth-188-189.AC3.1

**This is a manual verification task. No code changes.**

**Important:** Wait at least 2 hours after AAF registration (Task 1) before testing.

**Step 1: Test first-time AAF login**

1. Start the production app
2. Click "Login with AAF"
3. Authenticate with a real MQ staff account (via MQ OneID)
4. Verify:
   - Redirected back to app with active session
   - Local user record created (AC3.1)
   - User has `instructor` role if staff affiliation present (from Phase 2)

**Step 2: Test returning user**

1. Log out
2. Log in again with the same MQ account
3. Verify:
   - Existing user record updated, not duplicated (AC1.2)
   - Session active

**Step 3: Test with student account (if available)**

1. Log in with an MQ student account
2. Verify:
   - User provisioned without `instructor` role
   - `is_privileged_user()` returns False

**Step 4: Test invalid/expired SSO token (AC1.4)**

1. Navigate directly to `/auth/sso/callback?token=expired-or-malformed-token`
2. Verify:
   - Error message displayed (not a crash or blank page)
   - No session created (user is not logged in)
   - Redirect back to login page

**Diagnostic checklist (same as Phase 1 Task 5):**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "AAF error" or no redirect | AAF propagation not complete | Wait 2 hours, retry |
| redirect_uri_mismatch | Production redirect URI doesn't match | Verify byte-for-byte match in AAF manager |
| Missing trusted_metadata | Attribute mapping not applied | Check Stytch dashboard mapping config |
| User gets no roles | `eduperson_affiliation` not released | Check AAF attribute release for the client |

<!-- END_TASK_3 -->

---

## Phase Completion Criteria

**Verifies: None** — this is an infrastructure phase. All verification is manual.

Phase 5 is complete when:
1. Production AAF OIDC client registered (Task 1)
2. Stytch connection updated to production (Task 2)
3. Real MQ staff can authenticate end-to-end (Task 3)
4. Returning users are updated, not duplicated (Task 3)
