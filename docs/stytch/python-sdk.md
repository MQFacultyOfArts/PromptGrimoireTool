---
source: https://github.com/stytchauth/stytch-python
fetched: 2025-01-13
summary: Stytch Python SDK - magic links, sessions, async support
---

# Stytch Python SDK

Official Python SDK for Stytch authentication. Supports Python 3.8+.

## Installation

```bash
pip install stytch
```

Latest: v13.21.0 (Sept 2025), MIT licensed.

## Basic Setup

```python
import stytch

client = stytch.Client(
    project_id="your-project-id",
    secret="your-secret",
)
```

Credentials available in Stytch Dashboard.

## Magic Links

### Login or Create Flow

```python
# Send a magic link email
login_or_create_resp = client.magic_links.email.login_or_create(
    email="user@example.com",
    login_magic_link_url="https://example.com/authenticate",
    signup_magic_link_url="https://example.com/authenticate",
)
print(login_or_create_resp)  # Responses are fully-typed pydantic objects

# Authenticate the token from the magic link
auth_resp = client.magic_links.authenticate(
    token="token-from-magic-link",
)
print(auth_resp)
```

## Async Support

Every endpoint supports async by appending `_async`:

```python
login_or_create_resp = await client.magic_links.email.login_or_create_async(
    email="sandbox@stytch.com",
    login_magic_link_url="https://example.com/authenticate",
    signup_magic_link_url="https://example.com/authenticate",
)
```

## Error Handling

```python
from stytch.core.response_base import StytchError

try:
    auth_resp = await client.magic_links.authenticate_async(token="token")
except StytchError as error:
    if error.details.error_type == "invalid_token":
        print("Whoops! Try again?")
except Exception as error:
    # Handle other errors
    pass
```

## B2C vs B2B

Stytch offers two products:

- **Consumer (B2C)**: Individual user auth - magic links, passkeys, OAuth
- **B2B SaaS**: Organization-based auth with RBAC, SSO, SCIM

For PromptGrimoire (classroom tool with individual students/instructors):

- **B2C** is simpler for individual user authentication
- **B2B** provides built-in RBAC and organization (class) management

Decision needed: Do we want Stytch to manage class membership, or roll our own?

## Resources

- GitHub: https://github.com/stytchauth/stytch-python
- PyPI: https://pypi.org/project/stytch/
- B2C Quickstart: https://stytch.com/docs/quickstarts/python
- B2B Quickstart: https://stytch.com/docs/b2b/quickstarts/python
