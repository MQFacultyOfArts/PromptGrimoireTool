---
source: https://stytch.com/docs/b2b/api/create-saml-connection
fetched: 2025-01-15
library: stytch
summary: SAML SSO connections - integrate SAML identity providers including AAF
---

# SAML Connection

Configure SAML-based SSO for Organizations.

## Endpoint

**POST** `https://test.stytch.com/v1/b2b/sso/saml/{organization_id}`

## Create SAML Connection

```python
import stytch

client = stytch.B2BClient(
    project_id="PROJECT_ID",
    secret="SECRET"
)

response = await client.sso.saml.create_connection_async(
    organization_id="org-xxx",
    display_name="University SAML"
)

# Response includes ACS URL and metadata needed for IdP configuration
connection = response.connection
acs_url = connection.acs_url
audience_uri = connection.audience_uri
```

## Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `organization_id` | string | UUID of the Organization (path param) |
| `display_name` | string | Human-readable connection name |

## Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `identity_provider` | string | Predefined IdP type for specialized handling |

## Supported Identity Providers

- Okta
- Microsoft Entra (Azure AD)
- Google Workspace
- Keycloak
- JumpCloud
- OneLogin
- PingFederate
- Shibboleth
- Generic

## Response Object

```json
{
  "status_code": 200,
  "request_id": "UUID",
  "connection": {
    "organization_id": "org-xxx",
    "connection_id": "saml-connection-xxx",
    "status": "pending",
    "display_name": "University SAML",
    "acs_url": "https://test.stytch.com/v1/b2b/sso/saml/acs",
    "audience_uri": "https://stytch.com/...",
    "signing_certificates": [
      {
        "certificate": "...",
        "expires_at": "2025-12-31T00:00:00Z"
      }
    ],
    "attribute_mapping": {}
  }
}
```

## Configure IdP Metadata

After creating, update with IdP-provided metadata:

```python
response = await client.sso.saml.update_connection_async(
    organization_id="org-xxx",
    connection_id="saml-connection-xxx",
    idp_entity_id="https://idp.university.edu/entity",
    idp_sso_url="https://idp.university.edu/sso",
    x509_certificate="-----BEGIN CERTIFICATE-----\n...",
    attribute_mapping={
        "email": "urn:oid:0.9.2342.19200300.100.1.3",
        "first_name": "urn:oid:2.5.4.42",
        "last_name": "urn:oid:2.5.4.4"
    }
)
```

## RBAC Authorization

Pass session headers for RBAC enforcement:

```python
response = await client.sso.saml.create_connection_async(
    organization_id="org-xxx",
    display_name="University SAML",
    method_options={
        "authorization": {
            "session_token": "admin_session_token"
        }
    }
)
```

---

# AAF Rapid IdP Integration

## Overview

AAF (Australian Access Federation) provides identity federation for Australian research and education institutions. **Rapid IdP is a SAML-only service** - OIDC is not supported.

## Rapid IdP Modes

1. **Virtual mode**: User data stored in Rapid IdP database (for orgs without LDAP)
2. **Delegate mode**: Connects to external LDAP (AD, OpenLDAP)
3. **Proxy mode**: Integrates with existing SAML providers (Entra ID, Okta, Ping)

## Integration Steps

### 1. Register with AAF

Contact support@aaf.edu.au to set up Rapid IdP for your organization.

### 2. Get AAF Metadata

AAF provides:
- IdP Entity ID
- SSO URL
- X.509 Certificate
- Attribute mappings (eduPersonPrincipalName, mail, displayName, etc.)

### 3. Create Stytch SAML Connection

```python
# Create connection
response = await client.sso.saml.create_connection_async(
    organization_id="org-xxx",
    display_name="AAF Login",
    identity_provider="shibboleth"  # AAF uses Shibboleth
)

# Get ACS URL and Audience URI from response
acs_url = response.connection.acs_url
audience_uri = response.connection.audience_uri
```

### 4. Configure AAF with Stytch Metadata

Provide to AAF:
- **ACS URL** (Assertion Consumer Service): From Stytch response
- **Audience URI** (Entity ID): From Stytch response
- **Required attributes**: email, displayName

### 5. Update Stytch with AAF Metadata

```python
response = await client.sso.saml.update_connection_async(
    organization_id="org-xxx",
    connection_id="saml-connection-xxx",
    idp_entity_id="https://rapid.aaf.edu.au/idp/shibboleth",
    idp_sso_url="https://rapid.aaf.edu.au/idp/profile/SAML2/Redirect/SSO",
    x509_certificate="-----BEGIN CERTIFICATE-----\n...",
    attribute_mapping={
        "email": "mail",
        "first_name": "givenName",
        "last_name": "sn"
    }
)
```

## AAF Attributes

Common attributes from AAF:

| Attribute | OID | Description |
|-----------|-----|-------------|
| mail | urn:oid:0.9.2342.19200300.100.1.3 | Email address |
| displayName | urn:oid:2.16.840.1.113730.3.1.241 | Full name |
| givenName | urn:oid:2.5.4.42 | First name |
| sn | urn:oid:2.5.4.4 | Last name (surname) |
| eduPersonPrincipalName | urn:oid:1.3.6.1.4.1.5923.1.1.1.6 | Unique identifier |
| eduPersonAffiliation | urn:oid:1.3.6.1.4.1.5923.1.1.1.1 | Role (student, faculty, staff) |

## PromptGrimoire Use Case

For Australian university deployments:
1. Create Organization per institution
2. Configure SAML connection with AAF Rapid IdP
3. Map eduPersonAffiliation to roles (student → Student, faculty → Instructor)
4. Students/staff log in with institutional credentials
