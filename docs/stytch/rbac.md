---
source: https://stytch.com/docs/b2b/api/rbac-resource-object
fetched: 2025-01-13
summary: Stytch RBAC model - resources, roles, permissions
---

# Stytch RBAC (B2B Only)

RBAC is only available in Stytch B2B product.

## Core Concepts

### Resources

Entities your application manages (documents, classes, conversations).

```json
{
  "resource_id": "documents",
  "actions": ["create", "read", "write", "delete"],
  "description": "Text files for collaboration"
}
```

- `resource_id`: Unique, human-readable identifier (cannot start with "stytch")
- `actions`: Array of valid operations
- Wildcard `"*"` grants all permissions

### Stytch Default Resources

Reserved resources provided by Stytch:

- `stytch.organization` - org management (update name, slug, SSO settings)
- `stytch.member` - member lifecycle (create, role assignment, delete)
- `stytch.sso` - SSO connection management
- `stytch.self` - personal profile modifications

### Roles

Named collections of permissions tied to personas:

- Admin: Full access
- Instructor: Create/manage content
- Student: Read/annotate

### RBAC Policy

All resources and roles stored in Project's RBAC Policy, managed via Stytch Dashboard.

## PromptGrimoire Mapping

If using Stytch B2B:

| Our Concept | Stytch Concept |
|-------------|----------------|
| Class | Organization |
| Student/Instructor | Member |
| Admin/Instructor/Student | Role |
| Conversation, Annotation | Custom Resource |

### Custom Resources We'd Define

```json
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

## Trade-off: B2B vs B2C

**B2B Pros:**

- Built-in org/class structure
- RBAC out of the box
- Member invitations handled
- SSO integration for enterprise

**B2B Cons:**

- More complex model
- Organizations are siloed (cross-class sharing needs work)
- May be overkill for simple class structures

**B2C + Custom RBAC:**

- Simpler auth flow
- We control class/role model in our DB
- More flexibility for grimoire sharing
- More code to maintain
