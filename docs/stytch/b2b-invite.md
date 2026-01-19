---
source: https://stytch.com/docs/b2b/api/send-invite-email
fetched: 2025-01-15
library: stytch
summary: B2B invitation emails - invite new Members to Organizations with roles
---

# B2B Send Invite Email

Send invitation emails to new Members to join an Organization.

## Endpoint

**POST** `https://test.stytch.com/v1/b2b/magic_links/email/invite`

## Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `organization_id` | string | UUID identifying the Organization |
| `email_address` | string | New Member's email address |

## Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `invite_redirect_url` | string | URL where Member completes invite |
| `invite_template_id` | string | Custom email template ID |
| `invited_by_member_id` | string | Member ID of the inviter |
| `name` | string | New Member's name |
| `trusted_metadata` | object | App data (not editable by frontend) |
| `untrusted_metadata` | object | App data (editable by frontend) |
| `locale` | string | Language (en, es, fr, pt-br) |
| `roles` | array | Role IDs to assign |
| `invite_expiration_minutes` | int | Link validity (5-10080 min, default: 10080 = 1 week) |

## RBAC Authorization

Pass session headers for RBAC enforcement:

```python
# Requires "create" permission on "stytch.member" resource
response = client.magic_links.email.invite(
    organization_id="org-xxx",
    email_address="newuser@example.com",
    roles=["role-instructor"],
    method_options={
        "authorization": {
            "session_token": "current_user_session_token"
        }
    }
)
```

## Python SDK Example

```python
import stytch

client = stytch.B2BClient(
    project_id="PROJECT_ID",
    secret="SECRET"
)

# Basic invite
response = await client.magic_links.email.invite_async(
    organization_id="org-xxx",
    email_address="student@example.com"
)

# Invite with roles and metadata
response = await client.magic_links.email.invite_async(
    organization_id="org-xxx",
    email_address="instructor@example.com",
    name="Jane Doe",
    roles=["role-instructor"],
    trusted_metadata={"department": "Computer Science"},
    invite_expiration_minutes=10080  # 1 week
)
```

## Response (HTTP 200)

```json
{
  "status_code": 200,
  "request_id": "UUID",
  "member_id": "member-xxx",
  "member": {
    "email_address": "newuser@example.com",
    "status": "invited",
    "roles": [{ "role_id": "role-instructor", "sources": [] }]
  },
  "organization": { ... }
}
```

## Common Errors

| Error Type | Description |
|------------|-------------|
| `duplicate_member_email` | Email already exists in Organization |
| `invalid_email` | Email format invalid |
| `invalid_email_for_invites` | Email doesn't comply with org restrictions |
| `no_invite_redirect_urls_set` | No redirect URL configured |
| `retired_member_email` | Email previously used, must unlink first |

## Revoking Invites

To revoke an invite, delete the Member:

```python
await client.organizations.members.delete_async(
    organization_id="org-xxx",
    member_id="member-xxx"
)
```

This deletes the Member and invalidates all invite emails.

## PromptGrimoire Use Case

Use invites for:
- Instructors inviting students to a class (Organization)
- Admins adding instructors with elevated roles
- Pre-provisioning class rosters
