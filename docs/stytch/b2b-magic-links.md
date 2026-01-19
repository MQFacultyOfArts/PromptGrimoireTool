---
source: https://stytch.com/docs/b2b/api/send-login-signup-email
fetched: 2025-01-15
library: stytch
summary: B2B magic link login/signup API - organization-scoped authentication
---

# B2B Magic Link Login/Signup Email

Send magic link emails to Members within an Organization.

## Endpoint

**POST** `https://test.stytch.com/v1/b2b/magic_links/email/login_or_signup`

## Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `organization_id` | string | UUID identifying the Organization (or use `organization_slug` / `organization_external_id`) |
| `email_address` | string | Member's email address |

## Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `login_redirect_url` | string | Backend endpoint for login verification |
| `signup_redirect_url` | string | Backend endpoint for signup verification |
| `pkce_code_challenge` | string | Base64url encoded SHA256 hash for device validation |
| `login_template_id` | string | Custom email template for login |
| `signup_template_id` | string | Custom email template for signup |
| `locale` | string | Language tag: "en", "es", "fr", "pt-br" (default: en) |
| `login_expiration_minutes` | int | Link validity (5-10080 min, default: 60) |
| `signup_expiration_minutes` | int | Link validity (5-10080 min, default: 60) |

## Python SDK Example

```python
import stytch

client = stytch.B2BClient(
    project_id="PROJECT_ID",
    secret="SECRET"
)

# Sync
response = client.magic_links.email.login_or_signup(
    organization_id="organization-test-07971b06-ac8b-4cdb-9c15-63b17e653931",
    email_address="user@example.com",
    login_redirect_url="https://yourapp.com/auth/callback",
    signup_redirect_url="https://yourapp.com/auth/callback"
)

# Async
response = await client.magic_links.email.login_or_signup_async(
    organization_id="org-xxx",
    email_address="user@example.com",
    login_redirect_url="https://yourapp.com/auth/callback",
    signup_redirect_url="https://yourapp.com/auth/callback"
)
```

## Response (HTTP 200)

```json
{
  "status_code": 200,
  "request_id": "UUID",
  "member_id": "member-xxx",
  "member_created": false,
  "member": {
    "email_address": "user@example.com",
    "email_address_verified": true,
    "status": "active",
    "name": "User Name",
    "mfa_enrolled": false,
    "is_admin": false,
    "roles": [],
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  },
  "organization": { ... }
}
```

## Member Status Flow

- **New email** → Creates Member with "pending" status, sends signup link
- **Invited email** → Sends signup link
- **Active email** → Sends login link

## Common Errors

| Error Type | Description |
|------------|-------------|
| `invalid_email` | Malformed email address |
| `email_jit_provisioning_not_allowed` | JIT provisioning disabled for org |
| `invalid_email_for_jit_provisioning` | Email domain not in allowlist |
| `operation_restricted_by_organization_auth_methods` | Auth method disabled |
| `duplicate_member_email` | Email already exists in org |

## Key Difference from B2C

B2B magic links are **organization-scoped**. The `organization_id` parameter is required, and the Member is associated with that specific Organization.
