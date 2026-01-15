---
source: https://stytch.com/docs/b2b/api/oidc-connection-object
fetched: 2025-01-15
library: stytch
summary: OIDC SSO connections - integrate external identity providers
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

## AAF Integration Note

**AAF (Australian Access Federation) uses SAML, not OIDC.** See [SAML Connection](sso-saml.md) for AAF Rapid IdP integration.
