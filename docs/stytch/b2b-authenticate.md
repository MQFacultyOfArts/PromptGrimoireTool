---
source: https://stytch.com/docs/b2b/api/authenticate-magic-link
fetched: 2025-01-15
library: stytch
summary: B2B magic link token authentication - creates sessions with MFA support
---

# B2B Magic Link Authentication

Authenticate a magic link token and create a session.

## Endpoint

**POST** `https://test.stytch.com/v1/b2b/magic_links/authenticate`

## Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `magic_links_token` | string | The token from the magic link URL |

## Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_token` | string | Reuse existing session |
| `session_jwt` | string | Reuse existing session via JWT |
| `session_duration_minutes` | int | Session lifetime (5-527040 min, default: 60) |
| `session_custom_claims` | map | Custom claims (max 4KB) |
| `pkce_code_verifier` | string | For PKCE validation |
| `intermediate_session_token` | string | For MFA flows |
| `locale` | string | Language for MFA passcode |

## Python SDK Example

```python
import stytch

client = stytch.B2BClient(
    project_id="PROJECT_ID",
    secret="SECRET"
)

# Sync
response = client.magic_links.authenticate(
    magic_links_token="token_from_url",
    session_duration_minutes=60 * 24 * 7  # 1 week
)

# Async
response = await client.magic_links.authenticate_async(
    magic_links_token="token_from_url",
    session_duration_minutes=10080  # 1 week
)

if response.member_authenticated:
    # Success - store session
    session_token = response.session_token
    member_id = response.member_id
    org_id = response.organization_id
else:
    # MFA required
    intermediate_token = response.intermediate_session_token
    # Use with OTP/TOTP endpoints
```

## Response (HTTP 200)

```json
{
  "status_code": 200,
  "request_id": "UUID",
  "member_id": "member-xxx",
  "organization_id": "org-xxx",
  "method_id": "email-xxx",
  "member_authenticated": true,
  "session_token": "secret_token",
  "session_jwt": "JWT_token",
  "intermediate_session_token": "",
  "member_session": {
    "member_session_id": "UUID",
    "member_id": "member-xxx",
    "organization_id": "org-xxx",
    "authentication_factors": [
      {
        "type": "magic_link",
        "delivery_method": "email",
        "email_factor": { "email_id": "...", "email_address": "..." }
      }
    ],
    "started_at": "2024-01-01T00:00:00Z",
    "last_accessed_at": "2024-01-01T00:00:00Z",
    "expires_at": "2024-01-08T00:00:00Z",
    "custom_claims": {}
  },
  "member": { ... },
  "organization": { ... }
}
```

## MFA Handling

When MFA is required, the response includes:
- `member_authenticated: false`
- `intermediate_session_token` (valid for 10 minutes)

Use the intermediate token with:
- `client.otps.sms.authenticate()`
- `client.totps.authenticate()`
- `client.recovery_codes.recover()`

## Session Notes

- **session_token**: Long-lived, use for server-side validation
- **session_jwt**: 5-minute lifetime, must be refreshed
- Custom claims cannot use reserved names (iss, sub, aud, exp, nbf, iat, jti)

## Common Errors

| Error Type | Description |
|------------|-------------|
| `invalid_token` | Token is invalid or expired |
| `pkce_mismatch` | PKCE verifier doesn't match challenge |
| `unauthorized_credentials` | Invalid API credentials |

## Member Status Update

If the Member's status is "pending" or "invited", authenticating automatically updates them to "active".
