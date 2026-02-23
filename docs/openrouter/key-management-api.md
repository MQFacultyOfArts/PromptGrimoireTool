---
source: https://openrouter.ai/docs/guides/overview/auth/management-api-keys
fetched: 2026-02-23
library: openrouter
summary: Programmatic API key provisioning with per-key budgets, expiry, and lifecycle management
---

# OpenRouter Key Management API

Requires a **management API key** (not a regular API key) for authentication.

## Create Key

```
POST https://openrouter.ai/api/v1/keys
Authorization: Bearer <management-key>
```

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Name for the key (min 1 char) |
| `limit` | number \| null | No | Spending limit in USD |
| `limit_reset` | string \| null | No | Reset period: `daily`, `weekly`, `monthly`, or null (no reset). Resets at midnight UTC; weeks Mon-Sun |
| `include_byok_in_limit` | boolean | No | Include BYOK usage in limit (default: false) |
| `expires_at` | string \| null | No | ISO 8601 UTC expiry timestamp |

### Example

```python
import requests

MANAGEMENT_API_KEY = "your-management-key"
BASE_URL = "https://openrouter.ai/api/v1/keys"

response = requests.post(
    f"{BASE_URL}/",
    headers={
        "Authorization": f"Bearer {MANAGEMENT_API_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "name": "student-alice@example.com-COMP1234",
        "limit": 5,  # $5 USD budget
        "limit_reset": "weekly",
        "expires_at": "2026-06-30T23:59:59Z"
    }
)

data = response.json()
api_key = data["key"]  # "sk-or-v1-..." — only returned ONCE
key_hash = data["data"]["hash"]  # for future management operations
```

### Response (201)

```json
{
  "key": "sk-or-v1-...",
  "data": {
    "hash": "a3f5c9d8e7b4f2a1...",
    "name": "student-alice@example.com-COMP1234",
    "label": "sk-or-v1-analytics-3f5c9d8e",
    "disabled": false,
    "limit": 5,
    "limit_remaining": 5,
    "limit_reset": "weekly",
    "usage": 0,
    "usage_daily": 0,
    "usage_weekly": 0,
    "usage_monthly": 0,
    "created_at": "2026-02-23T10:00:00Z",
    "expires_at": "2026-06-30T23:59:59Z"
  }
}
```

**Important:** The `key` field (actual API key string) is only returned at creation time. Store it immediately (encrypted at rest).

## List Keys

```
GET https://openrouter.ai/api/v1/keys
Authorization: Bearer <management-key>
```

Paginate with `?offset=100`. Returns usage stats (daily/weekly/monthly) per key.

## Get Key Details

```
GET https://openrouter.ai/api/v1/keys/{hash}
Authorization: Bearer <management-key>
```

## Update Key

```
PATCH https://openrouter.ai/api/v1/keys/{hash}
Authorization: Bearer <management-key>
```

### Update fields

```json
{
  "name": "Updated Key Name",
  "disabled": true,
  "limit": 10,
  "limit_reset": "daily",
  "include_byok_in_limit": false
}
```

Use `disabled: true` to temporarily suspend a key without deleting it.

## Delete Key

```
DELETE https://openrouter.ai/api/v1/keys/{hash}
Authorization: Bearer <management-key>
```

Permanently revokes the key.

## Provisioning Flow for Educational Use

1. Instructor enrols student in course
2. System creates OpenRouter key: `POST /api/v1/keys` with `name: "student-{email}-{course_code}"`, `limit: 5`, `limit_reset: "weekly"`, `expires_at: <semester_end>`
3. Store encrypted key + hash in `StudentAPIKey` table
4. Student's playground requests use their key server-side (never exposed to browser)
5. On unenrol or course end: `DELETE /api/v1/keys/{hash}` to revoke
6. Monitor usage via `GET /api/v1/keys` — flag students approaching limits
