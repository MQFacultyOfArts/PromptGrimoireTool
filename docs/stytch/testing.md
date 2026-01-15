---
source: https://stytch.com/docs/b2b/guides/testing/e2e-testing, sandbox-values
fetched: 2025-01-15
library: stytch
summary: Testing guide - E2E testing, sandbox values, test credentials
---

# Testing Guide

## Sandbox Test Values

**Use these for automated testing in test environment.**

### Magic Links - Organization Flow

| Value | Type |
|-------|------|
| `sandbox@stytch.com` | Test email |
| `organization-test-007d9d4a-deac-4a87-ba0a-e6e8afba4d4b` | Test org ID |

**Magic Link Tokens:**

| Token | Result |
|-------|--------|
| `DOYoip3rvIMMW5lgItikFK-Ak1CfMsgjuiCyI7uuU94=` | Success (200) |
| `3pzjQpgksDlGKWEwUq2Up--hCHC_0oamfLHyfspKDFU=` | Auth failure (401) |
| `CprTtwhnRNiMBiUS2jSLcWYrfuO2POeBNdo5HhW6qTM=` | Not found (404) |

### Magic Links - Discovery Flow

Same email and tokens as Organization flow.

### Usage

```python
# In tests, use sandbox values
response = await client.magic_links.authenticate_async(
    magic_links_token="DOYoip3rvIMMW5lgItikFK-Ak1CfMsgjuiCyI7uuU94="
)
assert response.status_code == 200
```

**Important:** Sandbox values only work when calling Stytch API directly. They do NOT work with frontend/mobile SDKs.

## E2E Testing Strategies

### Magic Link Bot Detection Bypass

Stytch has bot detection that interferes with automated tests. Solution:

```python
# DON'T: Follow the magic link redirect
# DO: Extract params and redirect to your own callback

def test_magic_link_flow(page):
    # Get magic link from email (via Mailosaur or similar)
    magic_link_url = get_magic_link_from_email()

    # Parse URL to extract token
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(magic_link_url)
    params = parse_qs(parsed.query)
    token = params['token'][0]

    # Navigate directly to your callback with the token
    page.goto(f"http://localhost:8080/auth/callback?token={token}")
```

### Generating Test Sessions

For tests that don't need to test login:

```python
@pytest.fixture
async def authenticated_session():
    """Create a test session using password auth."""
    # Use sandbox token directly
    response = await client.magic_links.authenticate_async(
        magic_links_token="DOYoip3rvIMMW5lgItikFK-Ak1CfMsgjuiCyI7uuU94=",
        session_duration_minutes=60
    )
    return response.session_token
```

### OAuth Testing

OAuth providers (Google, Microsoft) don't allow browser automation. Use alternative auth methods in E2E tests:
- Magic links with sandbox tokens
- Password auth for test accounts

### Rate Limiting

- Use test environment keys (different rate limits)
- Create multiple test accounts to distribute requests
- Add delays between rapid API calls if needed

## Testing with NiceGUI

### Unit Tests (Mock Stytch)

```python
from unittest.mock import AsyncMock, patch

async def test_auth_client_success():
    with patch("stytch.B2BClient") as mock_client:
        mock_client.return_value.magic_links.authenticate_async = AsyncMock(
            return_value=MockResponse(
                status_code=200,
                session_token="test-session",
                member_id="member-xxx"
            )
        )
        # Test your wrapper
```

### E2E Tests (Real Server)

```python
def test_login_page(page, app_server):
    """Test login page renders correctly."""
    page.goto(f"{app_server}/login")

    # Verify UI elements
    expect(page.get_by_test_id("email-input")).to_be_visible()
    expect(page.get_by_test_id("send-btn")).to_be_visible()

def test_callback_with_sandbox_token(page, app_server):
    """Test callback with sandbox token."""
    # Use sandbox token directly
    token = "DOYoip3rvIMMW5lgItikFK-Ak1CfMsgjuiCyI7uuU94="
    page.goto(f"{app_server}/auth/callback?token={token}")

    # Should authenticate and redirect
    expect(page).to_have_url(f"{app_server}/protected")
```

### Session Storage in Tests

NiceGUI's `app.storage.user` uses browser cookies. For E2E tests:

```python
# conftest.py
_SERVER_SCRIPT = """
# ... existing setup ...
os.environ['STORAGE_SECRET'] = 'test-secret'
ui.run(port=port, reload=False, show=False, storage_secret='test-secret')
"""
```
