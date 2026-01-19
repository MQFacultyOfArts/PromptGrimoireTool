---
source: https://trust.aaf.edu.au/rapid-idp/
fetched: 2025-01-15
library: aaf
summary: AAF Rapid IdP - SAML identity provider for Australian research/education
---

# AAF Rapid IdP

Australian Access Federation's hosted SAML Identity Provider for research and education institutions.

## Overview

Rapid IdP allows organizations to connect users to the AAF federation using their existing identity management systems. Users access federated services with the same credentials they use internally.

**Protocol Support: SAML only** - OIDC is not supported by Rapid IdP.

## Connection Modes

### 1. Virtual Mode

For organizations **without** existing identity directories.

- User data stored in Rapid IdP database
- Admin management interface provided
- Suitable for smaller organizations

### 2. Delegate Mode

Connects to **external LDAP** directories.

- Microsoft Active Directory
- OpenLDAP
- Other LDAP-compatible directories

Administrators configure LDAP credentials; Rapid IdP queries the directory during authentication.

### 3. Proxy Mode

Integrates with **organizational SAML providers**.

Supported IdPs:
- Microsoft Entra ID (Azure AD)
- Okta
- Ping Federate
- Other SAML 2.0 providers

Enables seamless access to both on-campus and federated services.

## Key Features

- **Credential isolation**: User passwords never leave home organization
- **Branding controls**: Customizable user-facing login pages
- **Attribute filtering**: Control which user data is shared
- **Bilateral agreements**: Support for non-AAF services
- **Cloud deployment**: AWS-hosted, auto-scaling, zero downtime

## Standard Attributes

AAF provides standard eduPerson attributes:

| Attribute | Description |
|-----------|-------------|
| mail | Email address |
| displayName | Full name |
| givenName | First name |
| sn | Surname |
| eduPersonPrincipalName | Unique identifier (usually email@institution) |
| eduPersonAffiliation | Role: student, faculty, staff, member |
| eduPersonScopedAffiliation | Role with scope (e.g., student@mq.edu.au) |

## Integration with Stytch

Since AAF uses **SAML only**, integrate via Stytch B2B SAML connections:

1. Create SAML connection in Stytch (use `identity_provider: "shibboleth"`)
2. Get ACS URL and Audience URI from Stytch
3. Register service with AAF via Rapid IdP admin interface
4. Configure attribute release policy in AAF
5. Update Stytch connection with AAF IdP metadata

See [Stytch SAML Documentation](../stytch/sso-saml.md) for implementation details.

## Contact

- Support: support@aaf.edu.au
- Documentation: https://support.aaf.edu.au/
