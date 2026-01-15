---
source: https://stytch.com/docs/api/magic-links
fetched: 2025-01-14
summary: Stytch magic link complete flow - send, callback, authenticate
---

# Stytch Magic Link Flow

Complete guide for implementing magic link authentication with NiceGUI.

## Overview

1. User enters email
2. App calls Stytch to send magic link
3. User clicks link in email
4. User redirected to your callback URL with token
5. App authenticates token with Stytch
6. Session created

## API Endpoints

### Login or Create (Recommended)

Creates user if new, sends login link if existing.

```python
from stytch import Client

client = Client(
    project_id="your-project-id",
    secret="your-secret",
)

# Send magic link
resp = client.magic_links.email.login_or_create(
    email="user@example.com",
    login_magic_link_url="https://yourapp.com/auth/callback",
    signup_magic_link_url="https://yourapp.com/auth/callback",
    login_expiration_minutes=60,  # 5 min to 7 days
    signup_expiration_minutes=10080,  # Default 1 week
)

print(resp.user_id)
print(resp.email_id)
print(resp.user_created)  # True if new user
```

### Send to Existing User

```python
resp = client.magic_links.email.send(
    email="user@example.com",
    login_magic_link_url="https://yourapp.com/auth/callback",
    signup_magic_link_url="https://yourapp.com/auth/callback",
)
```

### Invite New User

Creates user in pending state until they authenticate.

```python
resp = client.magic_links.email.invite(
    email="newuser@example.com",
    invite_magic_link_url="https://yourapp.com/auth/callback",
    invite_expiration_minutes=10080,  # 1 week
    name={
        "first_name": "John",
        "last_name": "Doe"
    }
)
```

### Create Embeddable Token

For custom delivery (not via Stytch email). Requires special access.

```python
resp = client.magic_links.create(
    user_id="user-test-xxx",
    expiration_minutes=60,
)

token = resp.token
# Send token via your own method
# User visits: https://yourapp.com/auth/callback?token={token}
```

## Authenticate Token

When user clicks magic link and arrives at callback URL:

```python
from stytch import Client
from stytch.core.response_base import StytchError

client = Client(
    project_id="your-project-id",
    secret="your-secret",
)

async def authenticate_magic_link(token: str):
    try:
        resp = await client.magic_links.authenticate_async(
            token=token,
            session_duration_minutes=60 * 24 * 7,  # 1 week session
        )
        return {
            "user_id": resp.user_id,
            "session_token": resp.session_token,
            "session_jwt": resp.session_jwt,
            "user": resp.user,
        }
    except StytchError as error:
        if error.details.error_type == "invalid_token":
            return {"error": "Invalid or expired token"}
        raise
```

## NiceGUI Integration

### Complete Example

```python
from nicegui import app, ui
from stytch import Client
import os

# Initialize Stytch client
stytch_client = Client(
    project_id=os.getenv("STYTCH_PROJECT_ID"),
    secret=os.getenv("STYTCH_SECRET"),
)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

@ui.page('/login')
def login_page():
    async def send_magic_link():
        email = email_input.value
        if not email:
            ui.notify("Please enter email", type="warning")
            return

        try:
            resp = await stytch_client.magic_links.email.login_or_create_async(
                email=email,
                login_magic_link_url=f"{BASE_URL}/auth/callback",
                signup_magic_link_url=f"{BASE_URL}/auth/callback",
            )
            ui.notify(f"Magic link sent to {email}!", type="positive")
            email_input.value = ""
        except Exception as e:
            ui.notify(f"Error: {e}", type="negative")

    with ui.card().classes('absolute-center'):
        ui.label('Login to PromptGrimoire').classes('text-h5')
        email_input = ui.input('Email', placeholder='you@example.com')
        ui.button('Send Magic Link', on_click=send_magic_link)


@ui.page('/auth/callback')
async def auth_callback():
    # Get token from URL query params
    token = app.storage.browser.get('stytch_token')

    # Alternative: parse from request
    # from starlette.requests import Request
    # token = request.query_params.get('token')

    if not token:
        ui.label('No token provided').classes('text-negative')
        ui.link('Back to login', '/login')
        return

    try:
        resp = await stytch_client.magic_links.authenticate_async(
            token=token,
            session_duration_minutes=60 * 24 * 7,
        )

        # Store session
        app.storage.user['session_token'] = resp.session_token
        app.storage.user['user_id'] = resp.user_id
        app.storage.user['email'] = resp.user.emails[0].email

        ui.notify('Login successful!', type='positive')
        ui.navigate.to('/dashboard')

    except Exception as e:
        ui.label(f'Authentication failed: {e}').classes('text-negative')
        ui.link('Try again', '/login')


@ui.page('/dashboard')
def dashboard():
    # Check if logged in
    if 'session_token' not in app.storage.user:
        ui.navigate.to('/login')
        return

    ui.label(f"Welcome, {app.storage.user.get('email', 'User')}!")
    ui.button('Logout', on_click=lambda: logout())

def logout():
    app.storage.user.clear()
    ui.navigate.to('/login')


ui.run(storage_secret='your-storage-secret')
```

### Callback URL Handling

The magic link URL contains the token as a query parameter:

```
https://yourapp.com/auth/callback?stytch_token_type=magic_links&token=ABC123...
```

Parse it in NiceGUI:

```python
from nicegui import app, ui
from urllib.parse import parse_qs, urlparse

@ui.page('/auth/callback')
async def callback(request):
    # Parse token from query string
    query = parse_qs(urlparse(str(request.url)).query)
    token = query.get('token', [None])[0]

    if token:
        # Authenticate with Stytch
        pass
```

## Session Management

### Validate Session

```python
async def validate_session(session_token: str):
    try:
        resp = await stytch_client.sessions.authenticate_async(
            session_token=session_token,
        )
        return resp.user
    except StytchError:
        return None
```

### Middleware Pattern

```python
from nicegui import app, ui

def require_auth(func):
    async def wrapper(*args, **kwargs):
        session_token = app.storage.user.get('session_token')
        if not session_token:
            ui.navigate.to('/login')
            return

        user = await validate_session(session_token)
        if not user:
            app.storage.user.clear()
            ui.navigate.to('/login')
            return

        return await func(*args, **kwargs)
    return wrapper

@ui.page('/protected')
@require_auth
async def protected_page():
    ui.label('Protected content')
```

## Error Handling

Common error types:

| Error Type | Meaning |
|------------|---------|
| `invalid_email` | Email format invalid |
| `invalid_token` | Token expired or invalid |
| `user_not_found` | User doesn't exist (for send) |
| `too_many_requests` | Rate limited |
| `unauthorized_credentials` | Invalid API credentials |

```python
from stytch.core.response_base import StytchError

try:
    resp = await client.magic_links.authenticate_async(token=token)
except StytchError as e:
    if e.details.error_type == "invalid_token":
        # Token expired or already used
        pass
    elif e.details.error_type == "too_many_requests":
        # Rate limited
        pass
```

## Configuration

### Dashboard Settings

Set these in Stytch Dashboard:
- Default login redirect URL
- Default signup redirect URL
- Default invite redirect URL
- Email templates (optional)

### Environment Variables

```bash
STYTCH_PROJECT_ID=project-test-xxx
STYTCH_SECRET=secret-test-xxx
BASE_URL=https://yourapp.com
```

## Async Support

All methods have async variants with `_async` suffix:

```python
# Sync
resp = client.magic_links.email.login_or_create(email="...")

# Async
resp = await client.magic_links.email.login_or_create_async(email="...")
```
