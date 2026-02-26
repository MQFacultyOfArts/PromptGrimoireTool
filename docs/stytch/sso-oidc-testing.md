---
source: https://stytch.com/docs/b2b/guides/sso/initial-setup, https://stytch.com/docs/b2b/guides/sandbox, https://stytch.com/docs/b2b/api/create-oidc-connection, https://stytch.com/docs/b2b/api/update-oidc-connection
fetched: 2026-02-26
library: stytch
summary: Stytch B2B SSO OIDC testing - sandbox setup, connection lifecycle, test IdP strategies, JIT provisioning
---

# Stytch SSO OIDC Testing & Sandbox

## Test Environment

**Base URLs:**
- API: `https://test.stytch.com/v1/b2b/`
- Public/Frontend: `https://test.stytch.com/v1/public/`
- Default redirect: `http://localhost:3000/authenticate`

Credentials from Stytch Dashboard: `project_id`, `secret`, `public_token`.

## OIDC Connection Lifecycle

### 1. Create Connection (starts "pending")

```python
response = await client.sso.oidc.create_connection_async(
    organization_id=org_id,
    display_name="AAF OIDC",
    identity_provider="generic",  # AAF not in predefined list
)
connection_id = response.connection.connection_id
redirect_url = response.connection.redirect_url
# redirect_url = https://test.stytch.com/v1/public/sso/oidc/{connection_id}/callback
# Register this redirect_url with AAF as the Redirect URI
```

### 2. Configure Connection (becomes "active")

**Auto-discovery**: When `issuer` is set, Stytch fetches `${issuer}/.well-known/openid-configuration` and auto-fills `authorization_url`, `token_url`, `userinfo_url`, `jwks_url`.

```python
response = await client.sso.oidc.update_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
    issuer="https://central.test.aaf.edu.au",  # test
    client_id="<AAF-CLIENT-ID>",
    client_secret="<AAF-CLIENT-SECRET>",
    # If auto-discovery works, these are optional:
    # authorization_url="https://central.test.aaf.edu.au/oidc/authorize",
    # token_url="https://central.test.aaf.edu.au/oidc/token",
    # userinfo_url="https://central.test.aaf.edu.au/oidc/userinfo",
    # jwks_url="https://central.test.aaf.edu.au/oidc/jwks",
    custom_scopes="openid profile email eduperson_affiliation schac_home_organization",
)
```

**If auto-discovery fails**: provide all URLs explicitly. Response includes `metadata_retrieval_error` warning.

### 3. Verify Status

```python
response = await client.sso.oidc.get_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
)
assert response.connection.status == "active"
```

### 4. Delete Connection

```python
await client.sso.oidc.delete_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
)
```

## SSO Authentication Flow

### Start SSO

```python
# Redirect user to:
sso_url = (
    f"https://test.stytch.com/v1/public/sso/start"
    f"?connection_id={connection_id}"
    f"&public_token={public_token}"
    f"&login_redirect_url={login_redirect}"
    f"&signup_redirect_url={signup_redirect}"
)
# Returns 302 → IdP authorization endpoint
```

### Handle Callback

User returns to your redirect URL with `?token=xxx&stytch_token_type=sso`:

```python
response = await client.sso.authenticate_async(
    sso_token=token,
    session_duration_minutes=10080,  # 7 days
)

if response.member_authenticated:
    session_token = response.session_token
    member = response.member
    # member.trusted_metadata has mapped IdP attributes
else:
    # MFA required
    intermediate_token = response.intermediate_session_token
```

### Response Fields

```python
response.member_id: str
response.organization_id: str
response.session_token: str
response.session_jwt: str
response.member_authenticated: bool
response.member.email_address: str
response.member.trusted_metadata: dict
response.member.roles: list
response.organization.organization_slug: str
```

## JIT Provisioning

Auto-create members on first SSO login:

```python
# Enable for specific connections
await client.organizations.update_async(
    organization_id=org_id,
    sso_jit_provisioning="RESTRICTED",
    sso_jit_provisioning_allowed_connections=[connection_id],
)
```

Options: `ALL_ALLOWED`, `RESTRICTED`, `NOT_ALLOWED`.

**Security**: At least one existing member must have a verified email with the same domain as new JIT-provisioned members.

## Attribute Mapping

Map IdP claims to `trusted_metadata`:

```python
attribute_mapping = {
    "email": "email",
    "first_name": "given_name",
    "last_name": "family_name",
    "idp_user_id": "sub",
}
```

- Custom attributes merge into `trusted_metadata`
- IdP-driven fields overwritten on every login
- Fields NOT deleted if IdP stops sending them — must delete explicitly via Update Member API

## Testing SSO Without a Real IdP

Stytch has **no built-in mock IdP**. Options:

1. **AAF test federation** — free, no subscription, immediate activation. See [AAF OIDC Integration](../aaf/oidc-integration.md)
2. **Free IdP sandbox** — Okta developer, Azure AD free tier, Google Workspace trial
3. **Password-based testing** — for E2E tests that don't verify SSO login itself:

```python
# Create test member with password
await client.organizations.members.create_async(
    organization_id=org_id,
    email_address="test@example.com",
)
# Authenticate via password (bypasses SSO)
response = await client.passwords.authenticate_async(
    email_address="test@example.com",
    password="testpassword123",
    organization_id=org_id,
)
```

**Note**: OAuth/SSO providers block automated browser logins — E2E tests should use password auth or mock auth client.

## Sandbox Test Values

Stytch provides special sandbox values for API-only testing (not frontend SDKs):
- Magic link email: `sandbox@stytch.com`
- OTP phone: `+10000000000`, code: `000000`
- Special tokens for 200/401/404 responses

## OIDC Role Assignment Limitation

**Important**: Stytch currently supports implicit role assignment only for SAML connections, NOT OIDC. For OIDC, assign roles via:
- Email domain-based implicit roles (`rbac_email_implicit_role_assignments`)
- Explicit role assignment after authentication
- Custom logic in your callback handler

## External SSO Connections

Share one AAF connection across multiple organisations (e.g. multiple units):

```python
await client.sso.external.create_connection_async(
    organization_id="receiving-org-id",
    external_organization_id="source-org-id",
    external_connection_id="source-connection-id",
    display_name="Shared AAF SSO",
)
```

## Session Types

| Aspect | Session JWT | Session Token |
|--------|-------------|---------------|
| Verification | Local (offline) | API call required |
| Data | Contains member/session info | Opaque 44-char string |
| Lifespan | 5-min expiry (auto-refreshed) | Valid until revoked |
| Revocation | Validates locally for 5 min post-revocation | Immediate |

Frontend SDK auto-stores both as cookies and refreshes JWT every 3 minutes.
