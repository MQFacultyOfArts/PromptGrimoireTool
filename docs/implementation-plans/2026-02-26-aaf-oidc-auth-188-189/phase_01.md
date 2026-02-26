# AAF OIDC Authentication — Implementation Plan

**Goal:** Get the existing AAF OIDC connection in Stytch working against the AAF test federation

**Architecture:** All SSO code is already implemented (callback route, authenticate_sso(), login button, config validation). This phase is purely Stytch dashboard + AAF test federation configuration — no code changes.

**Tech Stack:** Stytch B2B dashboard, AAF Federation Manager (test), Rapid IdP

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-02-26

---

## Acceptance Criteria Coverage

This phase verifies (manually):

### aaf-oidc-auth-188-189.AC1: AAF OIDC login works end-to-end
- **aaf-oidc-auth-188-189.AC1.1 Success:** MQ staff user clicks "Login with AAF", authenticates at AAF, returns to app with active session and local user record created
- **aaf-oidc-auth-188-189.AC1.3 Failure:** AAF authentication failure (cancelled, denied) returns user to login page with error message
- **aaf-oidc-auth-188-189.AC1.5 Edge:** SSO callback with missing token parameter shows error, not a crash

### aaf-oidc-auth-188-189.AC6: AAF test federation established
- **aaf-oidc-auth-188-189.AC6.1 Success:** Test OIDC client registered at `manager.test.aaf.edu.au` with valid credentials
- **aaf-oidc-auth-188-189.AC6.2 Success:** Test user exists in AAF test federation (VHO or Rapid IdP)
- **aaf-oidc-auth-188-189.AC6.3 Success:** Stytch OIDC connection works against test federation endpoints

---

<!-- START_TASK_1 -->
### Task 1: Register AAF Test Federation OIDC Client

**Verifies:** aaf-oidc-auth-188-189.AC6.1

**This is a manual/infrastructure task. No code changes.**

**Step 1: Get Stytch redirect URL**

In the Stytch B2B dashboard:
1. Navigate to Authentication > SSO
2. Find the existing OIDC connection (or create one if none exists)
3. Copy the `redirect_url` value — it will be in the format:
   `https://test.stytch.com/v1/b2b/sso/callback/{connection-id}`
4. Record the `connection_id` — this is the value for `STYTCH__SSO_CONNECTION_ID`

**Step 2: Register OIDC client at AAF test federation**

1. Go to `https://manager.test.aaf.edu.au/oidc/clients/new`
2. Authenticate with AAF test federation credentials
3. Register a new OIDC Relying Party with:
   - **Client name:** PromptGrimoire (Test)
   - **Redirect URI:** The exact Stytch redirect URL from Step 1 (byte-for-byte match required — protocol, case, trailing slashes all matter)
   - **Grant type:** Authorization Code
4. Record the `client_id` and `client_secret` immediately — the secret cannot be recovered later
5. Store both in a secure location (e.g., password manager, not in code)

**Verification:**
- OIDC client appears in AAF test federation manager
- `client_id` and `client_secret` are recorded

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create AAF Test Federation User

**Verifies:** aaf-oidc-auth-188-189.AC6.2

**This is a manual/infrastructure task. No code changes.**

**Step 1: Create test user in Rapid IdP**

1. Go to `https://rapididp.test.aaf.edu.au/`
2. Create a test user account with:
   - An email address (any test email)
   - `eduperson_affiliation` set to `staff` (for testing instructor role mapping)
   - `schac_home_organization` set to `mq.edu.au`
3. Create a second test user with:
   - `eduperson_affiliation` set to `student` (for testing unprivileged access)

**Verification:**
- Both test users exist in Rapid IdP
- Test users can authenticate at the AAF test federation login page

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Configure Stytch OIDC Connection

**Verifies:** aaf-oidc-auth-188-189.AC6.3

**This is a manual/infrastructure task. No code changes.**

**Step 1: Verify AAF discovery metadata**

Fetch `https://central.test.aaf.edu.au/.well-known/openid-configuration` and confirm it returns valid OIDC discovery metadata including:
- `issuer`
- `authorization_endpoint`
- `token_endpoint`
- `userinfo_endpoint`
- `jwks_uri`

**Step 2: Configure Stytch OIDC connection**

In the Stytch B2B dashboard, configure the SSO OIDC connection:

| Field | Value |
|-------|-------|
| `identity_provider` | `generic` |
| `issuer` | Copy the exact `issuer` value from the AAF discovery metadata (likely `https://central.test.aaf.edu.au`) — no trailing slash unless the metadata includes one |
| `client_id` | From AAF registration (Task 1) |
| `client_secret` | From AAF registration (Task 1) |

Stytch should auto-discover `authorization_url`, `token_url`, `userinfo_url`, and `jwks_url` from the issuer.

**Step 3: Configure OIDC attribute mapping**

In the Stytch OIDC connection settings, map AAF claims to `trusted_metadata`:
- `eduperson_affiliation` → `trusted_metadata.eduperson_affiliation`
- `schac_home_organization` → `trusted_metadata.schac_home_organization`

**Step 4: Configure custom scopes**

Set the OIDC connection scopes to:
`openid profile email eduperson_affiliation schac_home_organization`

**Verification:**
- Stytch OIDC connection shows status "Active" or "Connected"
- Discovery metadata was successfully fetched (endpoints populated)

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Configure Local Environment

**Verifies:** None (infrastructure setup)

**This is a manual/infrastructure task. Minimal config change.**

**Step 1: Set environment variables**

Add to the `.env` file in the development environment:

```
STYTCH__SSO_CONNECTION_ID=<connection-id-from-stytch>
STYTCH__PUBLIC_TOKEN=<public-token-from-stytch-dashboard>
```

The `public_token` is found in the Stytch dashboard under API Keys. The config validator (`sso_requires_public_token`) enforces that both are set together.

**Verification:**

Run the app: `uv run python -m promptgrimoire`

Expected: App starts without configuration validation errors. The "Login with AAF" button appears on the login page.

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: End-to-End AAF Login Verification

**Verifies:** aaf-oidc-auth-188-189.AC1.1, aaf-oidc-auth-188-189.AC1.3, aaf-oidc-auth-188-189.AC1.5, aaf-oidc-auth-188-189.AC6.3

**This is a manual verification task. No code changes.**

**Step 1: Test successful login**

1. Start the app: `uv run python -m promptgrimoire`
2. Navigate to the login page
3. Click "Login with AAF"
4. You should be redirected to AAF test federation login
5. Authenticate with the test staff user (created in Task 2)
6. After AAF authentication, you should be redirected back to the app
7. Verify:
   - Active session exists (you're logged in)
   - Local user record was created in the database
   - Auth method is "sso_aaf"

**Step 2: Test authentication failure**

1. Click "Login with AAF"
2. At the AAF login, cancel or deny the authentication
3. Verify: You're returned to the login page with an error message (not a crash)

**Step 3: Test missing token**

1. Navigate directly to `/auth/sso/callback` without any query parameters
2. Verify: Error message displayed, no crash (existing code handles this in `sso_callback()` in `pages/auth.py`)

**Abort condition check:**

If Step 1 fails after all configuration is verified correct:
- Check Stytch logs for the specific error
- If the error is in Stytch's OIDC handler (not configuration): **STOP. Do not proceed to Phase 2.** Return to brainstorming for an alternative approach.
- If the error is configuration: fix and retry

**Diagnostic checklist for common failures:**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "invalid_request" or redirect_uri_mismatch | Stytch redirect URL doesn't match AAF registration | Copy Stytch's exact redirect_url to AAF manager |
| "issuer mismatch" | Trailing slash or protocol mismatch in issuer URL | Use exact `issuer` value from AAF discovery metadata |
| Missing claims in trusted_metadata | Scopes not configured or attribute mapping missing | Verify scopes include `eduperson_affiliation`; check Stytch attribute mapping |
| AAF shows institution picker instead of direct login | SkipDS not configured | Acceptable UX — investigate passing `entityID` through Stytch in Phase 2 if needed |
| Stytch 500 error on token exchange | Token/secret mismatch or endpoint misconfiguration | Verify client_secret matches; check Stytch logs |

<!-- END_TASK_5 -->

---

## Phase Completion Criteria

**Verifies: None** — this is an infrastructure phase. All verification is manual.

Phase 1 is complete when:
1. AAF test OIDC client is registered (Task 1)
2. Test users exist in Rapid IdP (Task 2)
3. Stytch OIDC connection is configured and active (Task 3)
4. Local environment has SSO config (Task 4)
5. End-to-end login works with test user (Task 5, Step 1)
6. Error cases handled gracefully (Task 5, Steps 2-3)

**Commit:** No code commit for this phase (configuration only). If `.env` changes are needed, they are environment-specific and not committed.
