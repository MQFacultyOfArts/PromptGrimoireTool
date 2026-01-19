---
source: https://tutorials.aaf.edu.au/openid-connect-integration
fetched: 2025-01-15
library: aaf
summary: AAF OIDC integration - endpoints, scopes, claims, and registration process
---

# AAF OpenID Connect Integration

AAF supports OpenID Connect (OIDC) connectivity and operates an OpenID Provider (OP) that authenticates users across AAF subscriber Identity Providers.

## Test Federation Endpoints

```text
Discovery:     https://central.test.aaf.edu.au/.well-known/openid-configuration
Issuer:        https://central.test.aaf.edu.au
Authorization: https://central.test.aaf.edu.au/oidc/authorize
Token:         https://central.test.aaf.edu.au/oidc/token
UserInfo:      https://central.test.aaf.edu.au/oidc/userinfo
JWKS:          https://central.test.aaf.edu.au/oidc/jwks
```

## Supported Configuration

- **Response Types**: Authorization code flow only
- **Token Auth Methods**: Client secret basic and POST
- **ID Token Signing**: RS256

## Available Scopes and Claims

Attributes are requested through OAuth 2.0 scopes. Each scope returns specific claims.

| Scope | Returns |
|-------|---------|
| `openid` | sub (unique user ID), iss, aud, exp, iat, at_hash |
| `profile` | name, family_name, given_name, preferred_username |
| `email` | email address |
| `phone` | phone_number (rarely provided by AAF IdPs) |
| `aueduperson` | au_edu_person_shared_token |
| `eduperson_affiliation` | student, faculty, staff, member |
| `eduperson_assurance` | assurance level |
| `eduperson_orcid` | ORCID identifier |
| `eduperson_principal_name` | principal name (usually email@institution) |
| `eduperson_scoped_affiliation` | affiliation with institution scope |
| `schac_home_organization` | institution identifier |
| `schac_home_organization_type` | organization type |
| `home_organization` | organization name |

**Note**: A claim is only provided if the user's home organisation releases that attribute. Not all institutions support all attributes.

## Registration Process

### 1. Log into Federation Manager

Access the AAF Federation Manager portal.

### 2. Connect a New Service

Navigate to "Connect a New Service" → "OpenID Connect"

### 3. Provide Required Information

- **Name**: Descriptive service identifier
- **Description**: Service purpose
- **URL**: Application's primary web address (use `http` in development)
- **Redirect URL**: Endpoint receiving OIDC responses
- **Authentication Method**: "Secret" (server-side) or "Secret and PKCE" (enhanced security)
- **Organisation**: Must be an AAF subscriber

### 4. Receive Credentials

Upon registration you receive:

- **Identifier**: Client ID
- **Secret**: Client secret

**Critical**: The secret is shown only once. Copy it immediately.

### 5. Wait for Propagation

A ~2 hour delay occurs before the service is functional. This includes metadata generation and configuration. Attempting access during this window triggers an error.

## Configuring Scopes

Services can configure which scopes they request through the "Scopes" tab on the service page in Federation Manager. By default, all scopes are used unless specified otherwise.

## eduGAIN Access

To enable eduGAIN functionality (access to international research federations), contact AAF support. Note: eduGAIN is only available in production, not the test environment.

## Support

- Email: support@aaf.edu.au
- Phone: +61 7 3854 2353
- Portal: https://aaf.freshdesk.com/support/home/

## References

- [OpenID OIDC Core Spec](https://openid.net/specs/openid-connect-core-1_0.html)
- [AAF Tutorials](https://tutorials.aaf.edu.au/)
