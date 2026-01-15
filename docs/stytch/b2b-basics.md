---
source: https://stytch.com/docs/b2b/guides/what-is-stytch-b2b-auth
fetched: 2025-01-15
library: stytch
summary: B2B fundamentals - Organizations, Members, settings, core flows, features
---

# Stytch B2B Basics

## Data Model Overview

Stytch's B2B auth is built around two core entities: **Organizations** and **Members**.

### Organizations

Represents an instance or tenant in your application, typically mapping to each top-level customer.

Key characteristics:
- **Account Ownership**: Holds subscription/contract, manages billing
- **Access Management**: Determines who can access and what they can do
- **User Management**: Admin actions like updating emails, resetting MFA
- **Data Segregation**: Isolated from other tenants

**Unique identifiers:**
1. `organization_id`: Stytch-generated unique ID
2. `organization_slug`: Human-readable alphanumeric string (e.g., `acme-corp` in `acme-corp.yourapp.com`)

### Members

Represents an individual end user's account within an Organization, identified by email.

- Emails are unique **within** the Organization
- One person can belong to **multiple Organizations** with the same email
- Each Organization has its own Member record for that person

**Unique identifiers:**
1. `member_id`: Globally unique across all Organizations
2. `email_address`: Unique within the Organization

## Organization Settings

Comprehensive admin controls per Organization:

| Setting | Description |
|---------|-------------|
| **Approved auth methods** | Which primary auth methods members can use (SSO only, magic links, etc.) |
| **JIT Provisioning** | Auto-create accounts for users meeting criteria (email domain, SSO, OAuth) |
| **Invites** | Allow any domain, restrict to allowed domains, or disable |
| **SSO connections** | Multiple IdP connections with JIT and auto role assignment |
| **MFA policies** | Require MFA for all members, specify allowed methods |
| **RBAC assignment** | Assign roles via SCIM groups, SSO connection, or email domain |
| **Custom metadata** | Store app-specific attributes |

```json
{
  "organization_id": "organization-test-07971b...",
  "organization_name": "Organization A",
  "organization_slug": "org-a",
  "email_invites": "ALL_ALLOWED",
  "email_jit_provisioning": "RESTRICTED",
  "email_allowed_domains": ["stytch.com"],
  "allowed_auth_methods": ["sso", "magic_links"],
  "mfa_policy": "OPTIONAL"
}
```

## Member Settings

- **RBAC assignment**: Multiple roles, direct or automatic
- **Breakglass**: Bypass auth requirements for maintenance
- **MFA enrollment**: Opt-in even if org doesn't require
- **Custom metadata**: App-specific attributes

## Member Provisioning Methods

1. **Invite**: Email Magic Link invitation
2. **JIT Provisioning**: Auto-create if user meets requirements
3. **SCIM**: Sync from workforce IdP automatically
4. **Manual**: Direct API calls

## Core Authentication Flows

### Discovery Flow

User authenticates **before** specifying Organization:

1. User enters email/authenticates
2. Shown all Organizations they can access:
   - Current active memberships
   - Pending invites
   - Eligible via email domain/JIT
3. User selects Organization
4. Stytch enforces that org's auth requirements
5. Session created

**Benefits:**
- Centralized login page
- Users find existing accounts instead of creating duplicates
- Improves conversion by consolidating usage

### Organization-Specific Login

User goes to tenant-specific page (e.g., `acme-corp.yourapp.com`):

1. User sees auth methods allowed by that Organization
2. Authenticates directly
3. Session created for that Organization

**Use case:** Enterprise customers with SSO configured.

### Organization Switching

Switch between Organizations without logging out:

1. Surface other Organizations user belongs to
2. Prompt for step-up auth if needed
3. "Exchange" current session for new Organization's session

## Feature Overview

### Multi-tenancy
- Organizations as first-class entities
- Per-org settings, invites, provisioning
- Account deduplication handled

### Single Sign-On (SSO)
- SAML and OIDC protocols
- Multiple connections per Organization
- JIT provisioning per connection

### Sessions
- `session_token`: For server-side validation
- `session_jwt`: For client-side (5-min lifetime, refresh required)
- Custom claims support

### Auth Methods

**Primary:**
- Email Magic Links
- Passwords
- SSO (SAML/OIDC)
- OAuth

**MFA:**
- OTP (SMS/Email)
- TOTP (Authenticator apps)

### RBAC
- Resources, Actions, Roles, Permissions
- Wildcard permissions for admins
- Multi-tenant aware

### SCIM
- Automated provisioning from workforce IdP
- Real-time sync of user data

### Webhooks
- Out-of-band updates (SCIM events, Dashboard changes)

### Device Fingerprinting
- Account takeover protection
- Per-request fingerprinting

### Protected Email Magic Links
- Bypass enterprise security link scanners

## PromptGrimoire Mapping

| Stytch Concept | PromptGrimoire |
|----------------|----------------|
| Organization | Class |
| Member | Student/Instructor |
| SSO Connection | AAF Rapid IdP |
| RBAC Role | instructor, student, admin |
| JIT Provisioning | Auto-enroll via AAF |

## Why B2B (Not B2C)

B2C is user-first. B2B is **organization-first**:

- Organizations control auth methods
- Organizations enforce MFA
- Organizations manage roles
- Organizations approve/deny access

This enables:
- Enterprise requirements (Fortune 100)
- PLG/prosumer motions
- Diverse auth flows per customer
- Complex permission settings
