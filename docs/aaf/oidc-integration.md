---
source: https://tutorials.aaf.edu.au/openid-connect-integration, https://central.aaf.edu.au/.well-known/openid-configuration
fetched: 2026-02-26
library: aaf
summary: AAF OIDC integration - endpoints, scopes, claims, registration, skipDS, and attribute-based authorisation
---

# AAF OpenID Connect Integration

AAF operates an OpenID Provider (OP) via **AAF Central** that authenticates users across AAF subscriber Identity Providers. This is the recommended modern integration path (over SAML/Rapid Connect).

## Production Endpoints

```text
Discovery:     https://central.aaf.edu.au/.well-known/openid-configuration
Issuer:        https://central.aaf.edu.au
Authorization: https://central.aaf.edu.au/oidc/authorize
Token:         https://central.aaf.edu.au/oidc/token
UserInfo:      https://central.aaf.edu.au/oidc/userinfo
JWKS:          https://central.aaf.edu.au/oidc/jwks
Service Docs:  https://central.aaf.edu.au/oidc/documentation
```

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

- **Response Types**: `code` (authorization code flow only)
- **Grant Types**: `authorization_code`
- **Token Auth Methods**: `client_secret_basic`, `client_secret_post`
- **ID Token Signing**: RS256
- **UserInfo Signing**: RS256
- **Subject Types**: public
- **Response Modes**: query
- **PKCE Support**: S256, plain

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

## Standard OIDC Flow

Five-step authorization code flow:

1. RP (Client) sends authorization request to AAF Central OP
2. OP authenticates the end-user via their home institution IdP
3. OP responds with an ID Token and Access Token
4. RP sends Access Token to the UserInfo endpoint
5. UserInfo endpoint returns claims about the end-user

## Skipping the Discovery Service (SkipDS)

By default, AAF shows a discovery service page where users select their institution. To bypass this and send users directly to a specific IdP:

Add the `entityID` parameter (URL-encoded) to the authorization request:

```
GET /oidc/authorize?client_id=123456789
    &redirect_uri=https://example.com/aaf/callback
    &nonce=123456
    &state=6789
    &entityID=https%3A%2F%2Fvho.aaf.edu.au%2Fidp%2Fshibboleth
```

This is useful for deploying within a single institution (e.g. Macquarie University) — configure one login button that skips straight to MQ's IdP.

**Limitation**: Requires the ability to add extra authorization parameters to the OIDC flow. If using Stytch SSO, this parameter must be passable through Stytch's SSO start flow.

## Attribute-Based Authorisation

Key attributes for access control decisions:

| Attribute | Use Case |
|-----------|----------|
| `eduPersonEntitlement` | User's rights to specific resources (IdP-delegated authorisation) |
| `eduPersonAffiliation` | Organisational relationship (student, staff, faculty, member) — good for site-licence access |
| `eduPersonScopedAffiliation` | Multivalued affiliation with institution scope — use when SP needs domain confirmation |
| `schacHomeOrganization` | Home institution identifier — institutional context |
| `mail` | Communication only (not for authorisation) |

**Demo app**: https://oidc-demo.aaf.edu.au/ — view actual attribute releases from your institution.

## Macquarie University

MQ has adopted AAF's Rapid IdP as their cloud identity solution. MQ users authenticate via OneID. See: https://aaf.edu.au/project/macquarie-university-rapid-idp/

## Support

- Email: support@aaf.edu.au
- Phone: +61 7 3854 2353
- Portal: https://aaf.freshdesk.com/support/home/

## References

- [OpenID OIDC Core Spec](https://openid.net/specs/openid-connect-core-1_0.html)
- [AAF Tutorials](https://tutorials.aaf.edu.au/)
- [AAF OIDC Demo App](https://oidc-demo.aaf.edu.au/)
- [AAF Federation Manager (test)](https://manager.test.aaf.edu.au/)
- [AAF Federation Manager (production)](https://manager.aaf.edu.au/)
