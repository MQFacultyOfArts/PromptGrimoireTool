---
source: https://stytch.com/docs/b2b/api/oidc-connection-object, https://stytch.com/docs/b2b/guides/sso/backend, https://stytch.com/docs/b2b/api/sso-authenticate
fetched: 2026-02-26
library: stytch
summary: OIDC SSO connections - integrate external identity providers via Stytch, including AAF OIDC
---

# OIDC Connection Object

Configure OpenID Connect SSO for Organizations.

## Connection Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `organization_id` | string | UUID of the Organization |
| `connection_id` | string | Unique connection identifier |
| `display_name` | string | Human-readable name |
| `status` | string | "pending" or "active" |
| `redirect_url` | string | Callback URL for IdP |

## IdP Configuration

| Field | Type | Description |
|-------|------|-------------|
| `issuer` | string | HTTPS URL identifying the IdP |
| `client_id` | string | OAuth 2.0 client identifier |
| `client_secret` | string | OAuth 2.0 client credential |
| `authorization_url` | string | IdP's OAuth login endpoint |
| `token_url` | string | Token exchange endpoint |
| `userinfo_url` | string | UserInfo endpoint |
| `jwks_url` | string | JSON Web Key Set location |

## Supported Identity Providers

Stytch has specialized handling for 16+ providers:

- ClassLink
- CyberArk
- Duo
- Google Workspace
- JumpCloud
- Keycloak
- miniOrange
- Microsoft Entra (Azure AD)
- Okta
- OneLogin
- PingFederate
- Rippling
- Salesforce
- Shibboleth
- Generic (custom implementations)

## Advanced Options

```python
# Custom scopes (replaces default: openid email profile)
custom_scopes = "openid email profile groups"

# Attribute mapping to member metadata
attribute_mapping = {
    "department": "custom_claims.department",
    "employee_id": "custom_claims.emp_id"
}
```

## Create OIDC Connection

```python
import stytch

client = stytch.B2BClient(
    project_id="PROJECT_ID",
    secret="SECRET"
)

response = await client.sso.oidc.create_connection_async(
    organization_id="org-xxx",
    display_name="University SSO"
)

# Response includes connection_id and configuration URLs
connection_id = response.connection.connection_id
```

## Update Connection with IdP Details

```python
response = await client.sso.oidc.update_connection_async(
    organization_id="org-xxx",
    connection_id="oidc-connection-xxx",
    issuer="https://idp.university.edu",
    client_id="stytch-client-id",
    client_secret="stytch-client-secret",
    authorization_url="https://idp.university.edu/oauth2/authorize",
    token_url="https://idp.university.edu/oauth2/token",
    userinfo_url="https://idp.university.edu/oauth2/userinfo",
    jwks_url="https://idp.university.edu/oauth2/keys"
)
```

## AAF Integration via OIDC

AAF Central supports OIDC as well as SAML. For OIDC integration with AAF via Stytch:

- Use `identity_provider: "generic"` (AAF is not in Stytch's predefined list)
- Configure with AAF Central production endpoints:

```python
await client.sso.oidc.update_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
    issuer="https://central.aaf.edu.au",
    client_id="<AAF-CLIENT-ID>",
    client_secret="<AAF-CLIENT-SECRET>",
    authorization_url="https://central.aaf.edu.au/oidc/authorize",
    token_url="https://central.aaf.edu.au/oidc/token",
    userinfo_url="https://central.aaf.edu.au/oidc/userinfo",
    jwks_url="https://central.aaf.edu.au/oidc/jwks",
    custom_scopes="openid profile email eduperson_affiliation eduperson_scoped_affiliation schac_home_organization",
)
```

- Request AAF client credentials from https://manager.aaf.edu.au/oidc/clients/new
- Set Stytch's `redirect_url` as the AAF redirect URI during registration
- **Secret shown only once** — copy immediately

### Attribute Mapping for AAF

Map AAF-specific claims to Stytch member trusted_metadata:

```python
attribute_mapping = {
    "email": "email",
    "first_name": "given_name",
    "last_name": "family_name",
    "idp_user_id": "sub",
    # Custom AAF attributes flow to trusted_metadata
}
```

AAF edu-specific claims (eduperson_affiliation, schac_home_organization, etc.) will appear in the ID token and flow through to `trusted_metadata` via custom attribute mapping.

## SSO Authentication Flow (Backend)

### 1. Start SSO Login

Redirect user to Stytch SSO start endpoint:

```python
sso_url = (
    f"https://api.stytch.com/v1/public/sso/start"
    f"?connection_id={connection_id}"
    f"&public_token={public_token}"
    f"&login_redirect_url={login_redirect}"
    f"&signup_redirect_url={signup_redirect}"
)
```

### 2. Handle Callback

Stytch redirects back with `?token=xxx&stytch_token_type=sso`:

```python
response = await client.sso.authenticate_async(
    sso_token=token,
    session_duration_minutes=10080,  # 7 days
)

if response.member_authenticated:
    session_token = response.session_token
    session_jwt = response.session_jwt
    member = response.member
    # member.trusted_metadata contains mapped AAF attributes
else:
    # MFA required — use response.intermediate_session_token
    pass
```

### Response Structure

```python
response.member_authenticated: bool
response.session_token: str
response.session_jwt: str
response.member.member_id: str
response.member.email_address: str
response.member.trusted_metadata: dict  # Mapped IdP attributes
response.member.roles: list
response.organization.organization_id: str
response.organization.organization_slug: str
```

**Note**: All SDK methods have async variants (append `_async`).
