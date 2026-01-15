---
source: https://stytch.com/docs/b2b/quickstarts/python
fetched: 2025-01-15
library: stytch
summary: Python B2B quickstart - client setup, magic links, sessions
---

# B2B Python Quickstart

## Installation

```bash
pip install stytch
```

## Client Initialization

```python
import os
from stytch import B2BClient

client = B2BClient(
    project_id=os.getenv("STYTCH_PROJECT_ID"),
    secret=os.getenv("STYTCH_SECRET"),
    environment="test"  # or "live"
)
```

## Discovery Flow (Recommended for Multi-Org)

Discovery flow allows users to access multiple Organizations with one email.

### 1. Send Discovery Magic Link

```python
# User enters email, we send discovery link
response = await client.magic_links.email.discovery.send_async(
    email_address="user@example.com"
)
```

### 2. Handle Callback

```python
# User clicks link, we get token from URL
token = request.args.get("token")

# Authenticate and get Intermediate Session Token (IST)
response = await client.magic_links.discovery.authenticate_async(
    discovery_magic_links_token=token
)

ist = response.intermediate_session_token
discovered_orgs = response.discovered_organizations
```

### 3. Select or Create Organization

```python
# If user has existing orgs, let them choose
# If new user, create org for them

if discovered_orgs:
    # User selects org_id from list
    response = await client.discovery.intermediate_sessions.exchange_async(
        intermediate_session_token=ist,
        organization_id=selected_org_id,
        session_duration_minutes=60 * 24 * 7
    )
else:
    # Create new org
    response = await client.discovery.organizations.create_async(
        intermediate_session_token=ist,
        organization_name="New Org",
        session_duration_minutes=60 * 24 * 7
    )

session_token = response.session_token
member = response.member
organization = response.organization
```

## Direct Organization Flow

For single-org apps or when org is known upfront:

```python
# Send magic link scoped to specific org
response = await client.magic_links.email.login_or_signup_async(
    organization_id="org-xxx",
    email_address="user@example.com",
    login_redirect_url="https://app.com/auth/callback",
    signup_redirect_url="https://app.com/auth/callback"
)

# Authenticate callback
response = await client.magic_links.authenticate_async(
    magic_links_token=token_from_url,
    session_duration_minutes=10080  # 1 week
)

session_token = response.session_token
```

## Session Validation

```python
from stytch.core.response_base import StytchError

async def get_authenticated_member(session_token: str):
    """Validate session and return member info."""
    try:
        response = await client.sessions.authenticate_async(
            session_token=session_token
        )
        return {
            "member": response.member,
            "organization": response.organization,
            "session": response.member_session
        }
    except StytchError as e:
        if e.details.error_type == "session_not_found":
            return None
        raise
```

## Protected Route Pattern

```python
@app.route("/protected")
async def protected():
    session_token = request.cookies.get("session_token")
    if not session_token:
        return redirect("/login")

    auth = await get_authenticated_member(session_token)
    if not auth:
        return redirect("/login")

    return f"Welcome, {auth['member'].email_address}!"
```

## Logout

```python
@app.route("/logout")
async def logout():
    session_token = request.cookies.get("session_token")
    if session_token:
        await client.sessions.revoke_async(session_token=session_token)

    response = redirect("/login")
    response.delete_cookie("session_token")
    return response
```

## Error Handling

```python
from stytch.core.response_base import StytchError

try:
    response = await client.magic_links.authenticate_async(token=token)
except StytchError as e:
    error_type = e.details.error_type
    if error_type == "invalid_token":
        # Token expired or invalid
        pass
    elif error_type == "session_not_found":
        # Session doesn't exist
        pass
    else:
        raise
```
