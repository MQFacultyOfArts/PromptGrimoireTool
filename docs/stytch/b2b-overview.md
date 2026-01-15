---
source: https://stytch.com/docs/b2b/guides/what-is-stytch-b2b-auth
fetched: 2025-01-15
library: stytch
summary: B2B auth overview - Organizations, Members, Sessions, auth methods
---

# What is Stytch B2B Auth?

## Core Concepts

### Organizations

Represent customer instances/tenants in your application. Each Organization:
- Has a unique `organization_id`
- Has a human-readable `organization_slug`
- Handles account ownership, access management, user administration
- Provides data segregation between tenants

**PromptGrimoire mapping**: Organization = Class

### Members

Individual end users within an Organization:
- Identified primarily by email address
- One person can belong to **multiple Organizations** with the same email
- Each Organization maintains a separate Member record

**PromptGrimoire mapping**: Member = Student/Instructor

## B2B vs B2C

B2B is **organization-first**, not user-first:

- Organizations control authentication methods (magic links, SSO, passwords)
- Organizations enforce MFA policies
- Organizations manage role-based access
- Organizations approve/deny member access

This enables enterprise features like "IT admin can enforce SSO-only login for all employees."

## Authentication Methods

**Primary authentication:**
- Email magic links
- Passwords
- Single Sign-On (SAML/OIDC)
- OAuth (Google, Microsoft, etc.)

**Secondary authentication (MFA):**
- One-time passcodes (OTP) via SMS/email
- Time-based OTP (TOTP) via authenticator apps
- Recovery codes

## Sessions

After authentication, Stytch provides:

| Token | Use | Lifetime |
|-------|-----|----------|
| `session_token` | Server-side validation | Configurable (5 min - 1 year) |
| `session_jwt` | Client-side validation | Fixed 5 minutes, must refresh |

```python
# Validate session
response = await client.sessions.authenticate_async(
    session_token="user_session_token"
)
member = response.member
organization = response.organization
```

## Data Model

```
Project
└── Organization (Class)
    ├── Members (Students/Instructors)
    ├── SSO Connections
    ├── RBAC Roles
    └── Settings (auth methods, MFA policy)
```
