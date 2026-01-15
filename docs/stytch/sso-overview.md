---
source: https://stytch.com/docs/b2b/guides/sso/overview, initial-setup, external-connections
fetched: 2025-01-15
library: stytch
summary: SSO overview - SAML/OIDC setup, external connections, IdP configuration
---

# SSO Overview

Single Sign-On allows Members to authenticate using their organization's identity provider.

## Supported Protocols

| Protocol | Use Case | Recommendation |
|----------|----------|----------------|
| **SAML** | Enterprise IdPs, AAF | More commonly used by enterprises |
| **OIDC** | Modern IdPs, OAuth-based | Simpler to configure |

## SSO Connection Types

### Organization SSO Connection

Each Organization can configure their own IdP:
- SAML connection (Okta, Entra, AAF, etc.)
- OIDC connection (Google Workspace, Keycloak, etc.)

### External SSO Connection

Share an SSO connection across multiple Organizations:
- Useful for MSPs with multiple tenants
- Maintains security boundaries
- Requires explicit trust configuration

## Initial Setup Steps

### 1. Configure Redirect URLs

In Stytch Dashboard → Redirect URLs:
- Default: `http://localhost:3000/authenticate`
- Add your production callback URL

### 2. Create Organization

```python
response = await client.organizations.create_async(
    organization_name="University Class",
    organization_slug="cs101-2025"
)
org_id = response.organization.organization_id
```

### 3. Create SSO Connection

```python
# SAML (recommended for AAF)
response = await client.sso.saml.create_connection_async(
    organization_id=org_id,
    display_name="University SSO",
    identity_provider="shibboleth"  # For AAF
)

# OIDC
response = await client.sso.oidc.create_connection_async(
    organization_id=org_id,
    display_name="Google Workspace"
)
```

### 4. Configure IdP

From the connection response, get:
- **ACS URL** (SAML) or **Redirect URL** (OIDC)
- **Audience URI** / **Entity ID**

Provide these to your IdP administrator.

### 5. Update Connection with IdP Metadata

```python
# SAML
await client.sso.saml.update_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
    idp_entity_id="https://idp.university.edu/entity",
    idp_sso_url="https://idp.university.edu/sso",
    x509_certificate="-----BEGIN CERTIFICATE-----..."
)

# OIDC
await client.sso.oidc.update_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
    issuer="https://accounts.google.com",
    client_id="xxx.apps.googleusercontent.com",
    client_secret="xxx"
)
```

## SSO Authentication Flow

### 1. Start SSO

```python
# Redirect user to IdP
sso_url = f"https://test.stytch.com/v1/b2b/sso/start?connection_id={connection_id}&public_token={public_token}"
return redirect(sso_url)
```

### 2. Handle Callback

```python
# IdP redirects back with token
token = request.args.get("token")

response = await client.sso.authenticate_async(
    sso_token=token,
    session_duration_minutes=10080
)

session_token = response.session_token
member = response.member
```

## External Connections

Share IdP across Organizations (e.g., university with multiple classes):

```python
# In the receiving organization
response = await client.sso.external.create_connection_async(
    organization_id="receiving-org-id",
    external_organization_id="source-org-id",
    external_connection_id="source-connection-id",
    display_name="Shared University SSO"
)
```

Configure JIT provisioning and role assignments for external connections.

## PromptGrimoire Strategy

**For Australian universities (AAF):**
1. Create one Organization per class
2. Configure SAML connection with AAF Rapid IdP
3. Use external connections to share AAF across multiple classes

**Alternative auth:**
- Magic links as fallback for users outside AAF
- Useful for guest instructors, external collaborators
