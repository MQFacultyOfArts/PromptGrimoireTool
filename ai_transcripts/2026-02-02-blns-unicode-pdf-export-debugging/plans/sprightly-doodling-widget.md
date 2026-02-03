# AAF Integration Plan (via OIDC)

## Protocol Choice: OIDC

AAF supports both OIDC and SAML. Using **OIDC** because:

- AAF recommends it as "preferred option"
- Simpler configuration than SAML
- Stytch has full OIDC support

## Current State

Your auth system is **already complete** for SSO:

- [client.py](src/promptgrimoire/auth/client.py) - `authenticate_sso()` works for both SAML and OIDC
- [config.py](src/promptgrimoire/auth/config.py) - `STYTCH_SSO_CONNECTION_ID` already defined
- [auth.py](src/promptgrimoire/pages/auth.py) - "Login with AAF" button and `/auth/sso/callback` route exist
- Full test coverage with mock SSO tokens

## AAF Test Federation Endpoints

```text
Discovery:     https://central.test.aaf.edu.au/.well-known/openid-configuration
Issuer:        https://central.test.aaf.edu.au
Authorization: https://central.test.aaf.edu.au/oidc/authorize
Token:         https://central.test.aaf.edu.au/oidc/token
UserInfo:      https://central.test.aaf.edu.au/oidc/userinfo
JWKS:          https://central.test.aaf.edu.au/oidc/jwks
```

## Available Scopes

Request these in Stytch OIDC config:

- `openid` - Required (sub, iss, aud, exp, iat)
- `profile` - name, family_name, given_name, preferred_username
- `email` - email address
- `eduperson_affiliation` - student/faculty/staff role
- `eduperson_scoped_affiliation` - role with institution scope
- `schac_home_organization` - institution identifier

## What Needs to Be Done

### Phase 1: AAF Registration (Federation Manager)

1. Log into AAF Federation Manager
2. Navigate to "Connect a New Service" → "OpenID Connect"
3. Provide:
   - **Name**: PromptGrimoire
   - **Description**: Collaborative prompt iteration tool for education
   - **URL**: Your app URL
   - **Redirect URL**: Get from Stytch OIDC connection (create that first)
   - **Authentication Method**: "Secret" (server-side app)
   - **Organisation**: Your AAF subscriber org

4. Receive (copy immediately - secret shown only once):
   - **Client ID** (Identifier)
   - **Client Secret**

5. Wait ~2 hours for metadata propagation

### Phase 2: Stytch Dashboard Configuration

1. **Create OIDC Connection** (do this first to get redirect URL)
   - Stytch Dashboard → SSO → Create Connection
   - Type: OIDC, Provider: Generic
   - Enter AAF endpoints (see above)
   - Enter Client ID + Secret from AAF

2. **Configure Scopes**

   ```text
   openid profile email eduperson_affiliation
   ```

3. **Set Environment Variable**

   ```bash
   STYTCH_SSO_CONNECTION_ID=oidc-connection-xxx
   ```

### Phase 3: Role Mapping (eduperson_affiliation → Roles)

Configure in Stytch Dashboard or handle in code:

```text
faculty → instructor role
staff → instructor role
student → student role
```

## Optional Code Enhancements

### Enhanced Mock Testing

Enhance [mock.py](src/promptgrimoire/auth/mock.py) with AAF-specific tokens:

```python
MOCK_AAF_STUDENT_TOKEN = "mock-aaf-student-token"
MOCK_AAF_FACULTY_TOKEN = "mock-aaf-faculty-token"
```

This allows testing role mapping before AAF registration completes.

### Registration Runbook

Create `docs/aaf/registration-runbook.md` with step-by-step guide.

## Files to Modify

| File | Change |
| ---- | ------ |
| `.env` | Set `STYTCH_SSO_CONNECTION_ID` |
| `src/promptgrimoire/auth/mock.py` | Add AAF test tokens (optional) |
| `tests/unit/test_mock_client.py` | Test AAF scenarios (optional) |
| `docs/aaf/oidc-integration.md` | Cache AAF OIDC docs (endpoints, scopes, registration) |
| `docs/_index.md` | Update index with new AAF docs |

## Verification

1. Set `STYTCH_SSO_CONNECTION_ID` in `.env`
2. Run: `uv run pytest tests/e2e/test_auth_pages.py -k sso`
3. Manual: Click "Login with AAF" → verify redirect to Stytch SSO start URL
4. After AAF registration: Full end-to-end test with real AAF credentials
