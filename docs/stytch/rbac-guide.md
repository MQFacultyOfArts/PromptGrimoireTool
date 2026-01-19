---
source: https://stytch.com/docs/b2b/guides/rbac/overview, stytch-default, role-assignment
fetched: 2025-01-15
library: stytch
summary: RBAC guide - roles, permissions, default resources, role assignment
---

# RBAC Guide

Role-Based Access Control for managing permissions within Organizations.

## Core Concepts

### Resources

Entities your application manages:
- Documents, conversations, annotations
- Custom resources you define

```python
# Custom resource definition (via Dashboard or API)
{
    "resource_id": "conversations",
    "actions": ["create", "read", "annotate", "share", "delete"]
}
```

### Actions

Valid operations on a resource:
- CRUD: create, read, update, delete
- Custom: share, export, annotate

### Roles

Named collections of permissions:

```python
{
    "role_id": "instructor",
    "permissions": [
        {"resource_id": "conversations", "actions": ["*"]},
        {"resource_id": "annotations", "actions": ["create", "read", "update", "delete"]}
    ]
}
```

Wildcard `"*"` grants all current and future actions.

## Default Resources (stytch.*)

| Resource | Description |
|----------|-------------|
| `stytch.self` | Logged-in user's own profile |
| `stytch.organization` | Organization settings |
| `stytch.member` | All members in org |
| `stytch.sso` | SSO connections |
| `stytch.scim` | SCIM provisioning |

## Default Roles

### stytch_member

Auto-assigned to all members:
- All `stytch.self` permissions (update own profile)
- Cannot edit own roles

### stytch_admin

Auto-assigned to org creator:
- Full `stytch.organization` permissions
- Full `stytch.member` permissions
- Full `stytch.sso` permissions

## Role Assignment

### Explicit Assignment

Direct assignment via API:

```python
# Assign role when creating member
await client.organizations.members.create_async(
    organization_id="org-xxx",
    email_address="user@example.com",
    roles=["instructor"]
)

# Update existing member's roles
await client.organizations.members.update_async(
    organization_id="org-xxx",
    member_id="member-xxx",
    roles=["instructor", "content-creator"]
)

# Assign via invite
await client.magic_links.email.invite_async(
    organization_id="org-xxx",
    email_address="user@example.com",
    roles=["student"]
)
```

### Implicit Assignment

Automatic assignment based on conditions:

**By email domain:**
```python
await client.organizations.update_async(
    organization_id="org-xxx",
    rbac_email_implicit_role_assignments=[
        {"domain": "university.edu", "role_id": "instructor"},
        {"domain": "student.university.edu", "role_id": "student"}
    ]
)
```

**By SSO Connection:**
```python
# All users from this SSO get the role
await client.organizations.update_async(
    organization_id="org-xxx",
    sso_jit_provisioning="ALL_ALLOWED",
    sso_default_roles=["student"]
)
```

**By SSO IdP Group (SAML only):**
```python
# Map IdP groups to roles
await client.sso.saml.update_connection_async(
    organization_id="org-xxx",
    connection_id="saml-xxx",
    saml_group_implicit_role_assignments=[
        {"group": "Faculty", "role_id": "instructor"},
        {"group": "Students", "role_id": "student"}
    ]
)
```

## Checking Permissions

```python
# Roles are in the session, not the member object
response = await client.sessions.authenticate_async(
    session_token=session_token
)

roles = response.member_session.roles

# Check if user has permission
def has_permission(roles: list, resource: str, action: str) -> bool:
    # Implement based on your RBAC policy
    pass
```

## PromptGrimoire Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access to organization |
| `instructor` | Create/manage conversations, view all annotations |
| `student` | Read conversations, create own annotations |

### Custom Resources

```python
# Define in Stytch Dashboard
{
    "resource_id": "conversations",
    "actions": ["create", "read", "annotate", "share", "delete"]
}

{
    "resource_id": "annotations",
    "actions": ["create", "read", "update", "delete"]
}

{
    "resource_id": "tags",
    "actions": ["create", "read", "update", "delete"]
}
```
