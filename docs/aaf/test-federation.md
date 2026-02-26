---
source: https://support.aaf.edu.au/support/solutions/articles/19000096640-openid-connect-, https://manager.test.aaf.edu.au/, https://central.test.aaf.edu.au/.well-known/openid-configuration
fetched: 2026-02-26
library: aaf
summary: AAF test federation - free registration, test endpoints, VHO, Rapid IdP, development workflow
---

# AAF Test Federation

The test federation is **free, open, and requires no subscription**. Services activate immediately.

## Quick Start

1. Register OIDC client: https://manager.test.aaf.edu.au/oidc/clients/new
2. Provide: client name, description, organisation, redirect URI
3. Receive immediately: Client ID + Client Secret
4. **Secret shown only once** — copy immediately (can generate new one later)

## Test Endpoints

| Service | URL |
|---------|-----|
| OIDC Discovery | `https://central.test.aaf.edu.au/.well-known/openid-configuration` |
| Issuer | `https://central.test.aaf.edu.au` |
| Authorization | `https://central.test.aaf.edu.au/oidc/authorize` |
| Token | `https://central.test.aaf.edu.au/oidc/token` |
| UserInfo | `https://central.test.aaf.edu.au/oidc/userinfo` |
| JWKS | `https://central.test.aaf.edu.au/oidc/jwks` |
| Federation Manager | `https://manager.test.aaf.edu.au/` |
| Attribute Validator | `https://validator.test.aaf.edu.au/` |
| Federation Status | `https://status.test.aaf.edu.au/` |
| VHO (Virtual Home) | `https://vho.test.aaf.edu.au/` |
| Rapid IdP | `https://rapididp.test.aaf.edu.au/` |
| OIDC Demo App | `https://oidc-demo.aaf.edu.au/` |

## Test vs Production Differences

| Aspect | Test | Production |
|--------|------|------------|
| Subscription | Not required | Required (AAF subscriber) |
| Approval | Immediate activation | Approval required |
| Registration delay | None | ~2 hour propagation |
| IdP pool | Limited test IdPs | All subscriber institutions |
| Cost | Free | Subscription fee |
| eduGAIN | Not available | Available on request |

## Test Identity Providers

### Virtual Home Organisation (VHO)

`https://vho.test.aaf.edu.au/` — AAF-operated IdP for external affiliates.

- Create test user accounts for authentication testing
- Manage groups and affiliations
- Supports 2FA testing
- **EntityID** (for skipDS): `https://vho.test.aaf.edu.au/idp/shibboleth`

### Rapid IdP

`https://rapididp.test.aaf.edu.au/` — AAF's hosted cloud IdP service.

- Create test organisations and users
- No local infrastructure needed
- Macquarie University uses Rapid IdP in production

### OIDC Demo App

`https://oidc-demo.aaf.edu.au/` — test authentication flows and view attribute releases.

## OpenID Configuration (Test)

```json
{
  "issuer": "https://central.test.aaf.edu.au",
  "authorization_endpoint": "https://central.test.aaf.edu.au/oidc/authorize",
  "token_endpoint": "https://central.test.aaf.edu.au/oidc/token",
  "userinfo_endpoint": "https://central.test.aaf.edu.au/oidc/userinfo",
  "jwks_uri": "https://central.test.aaf.edu.au/oidc/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "subject_types_supported": ["public"],
  "code_challenge_methods_supported": ["S256", "plain"],
  "scopes_supported": [
    "openid", "profile", "email", "phone",
    "aueduperson", "eduperson_affiliation", "eduperson_assurance",
    "eduperson_orcid", "eduperson_principal_name",
    "schac_home_organization"
  ]
}
```

## Support

- Email: support@aaf.edu.au
- Phone: +61 7 3854 2353
- Portal: https://aaf.freshdesk.com/support/home/
