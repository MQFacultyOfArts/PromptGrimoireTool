# Spike 3 Code Review: Stytch Magic Link Authentication

## Executive Summary

**Overall Assessment: GOOD with CRITICAL issues requiring fixes**

Spike 3 implements Stytch B2B magic link and SSO authentication with a clean architecture: protocol-based abstraction, factory pattern for client creation, and proper mock/real client separation. The implementation demonstrates solid understanding of Stytch's B2B model and NiceGUI integration.

However, there are **2 critical issues**, **4 high-priority issues**, and several medium-priority items that must be addressed before merge.

---

## Critical Issues (Must Fix Before Merge)

### C1. Triplicated Role Extraction Logic Without Edge Case Handling

**Files:** [client.py:109-114](src/promptgrimoire/auth/client.py#L109-L114), [client.py:147-151](src/promptgrimoire/auth/client.py#L147-L151), [client.py:183-187](src/promptgrimoire/auth/client.py#L183-L187)

The same fragile role extraction logic appears three times:

```python
raw_roles = response.member_session.roles
if raw_roles and hasattr(raw_roles[0], "role_id"):
    roles = [role.role_id for role in raw_roles]
else:
    roles = list(raw_roles) if raw_roles else []
```

**Problems:**
1. **Crashes on empty list**: `raw_roles[0]` throws `IndexError` if `raw_roles = []`
2. **Code duplication**: Maintenance nightmare - fix in one place, forget the others
3. **No tests for edge cases**: Empty roles list, None values, mixed types untested

**Fix:**

```python
# Add to client.py as a static method or module function
def _extract_roles(raw_roles: list | None) -> list[str]:
    """Extract role IDs from Stytch response roles.

    Handles both object roles (with role_id attr) and string roles.
    """
    if not raw_roles:
        return []
    # Check first item to determine format
    if hasattr(raw_roles[0], "role_id"):
        return [role.role_id for role in raw_roles]
    return list(raw_roles)
```

Then replace all three instances with `roles = _extract_roles(response.member_session.roles)`

**Add tests for:**
- `raw_roles = []` (empty list)
- `raw_roles = None`
- `raw_roles = ["admin", "user"]` (string roles)
- `raw_roles = [Role("admin"), Role("user")]` (object roles)

---

### C2. SSO E2E Test Has Meaningless Assertion

**File:** [test_auth_pages.py:97-115](tests/e2e/test_auth_pages.py#L97-L115)

```python
def test_sso_start_redirects(self, page: Page, app_server: str):
    page.goto(f"{app_server}/login")
    page.get_by_test_id("sso-login-btn").click()
    page.wait_for_timeout(500)  # Arbitrary wait
    # This assertion is ALWAYS TRUE after the timeout!
    assert "mock.stytch.com" in page.url or page.url != f"{app_server}/login"
```

The `or` condition makes the test pass even if SSO does nothing. After `wait_for_timeout(500)`, the URL changes due to navigation attempt, making `page.url != app_server + "/login"` trivially true.

**Fix options:**

Option A: Test that navigation was attempted by checking for network error:
```python
def test_sso_start_redirects(self, page: Page, app_server: str):
    page.goto(f"{app_server}/login")

    # Intercept navigation to mock.stytch.com
    with page.expect_navigation(url=lambda u: "mock.stytch.com" in u):
        page.get_by_test_id("sso-login-btn").click()
```

Option B: Use route interception to verify the redirect URL:
```python
def test_sso_start_redirects(self, page: Page, app_server: str):
    page.goto(f"{app_server}/login")

    redirect_url = None
    def capture_redirect(route):
        nonlocal redirect_url
        redirect_url = route.request.url
        route.abort()  # Don't actually navigate

    page.route("**/mock.stytch.com/**", capture_redirect)
    page.get_by_test_id("sso-login-btn").click()
    page.wait_for_timeout(100)

    assert redirect_url is not None
    assert "connection_id=" in redirect_url
    assert "public_token=" in redirect_url
```

---

## High Priority Issues

### H1. Fixture Duplication in Unit Tests

**File:** [test_auth_client.py](tests/unit/test_auth_client.py)

The same `mock_stytch_client` fixture is defined **5 times** (lines 16-22, 110-116, 200-206, 264-270, 331).

**Fix:** Move to `conftest.py`:

```python
# tests/conftest.py
@pytest.fixture
def mock_stytch_client():
    """Create a mocked Stytch B2BClient."""
    with patch("promptgrimoire.auth.client.B2BClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client
```

---

### H2. No Session Validation on Protected Routes

**File:** [auth.py:208-215](src/promptgrimoire/pages/auth.py#L208-L215)

The `/protected` page only checks if `auth_user` exists in session storage. It never calls `validate_session()` to verify the session is still valid with Stytch.

```python
@ui.page("/protected")
async def protected_page() -> None:
    user = _get_session_user()
    if not user:  # Only checks local storage, not Stytch!
        ui.navigate.to("/login")
        return
```

**Problem:** If a session is revoked server-side (user deleted, password changed, admin revocation), the local session persists.

**Fix:**

```python
@ui.page("/protected")
async def protected_page() -> None:
    user = _get_session_user()
    if not user:
        ui.navigate.to("/login")
        return

    # Validate session is still active with Stytch
    auth_client = get_auth_client()
    result = await auth_client.validate_session(user["session_token"])
    if not result.valid:
        _clear_session()
        ui.navigate.to("/login")
        return

    # ... rest of page
```

Consider: This adds latency to every protected page load. You may want to:
- Cache validation for N minutes
- Only validate on certain actions (not every page view)
- Use session JWT for quick local validation + periodic refresh

---

### H3. Silent Failures Without Logging

**Files:** [client.py](src/promptgrimoire/auth/client.py), [auth.py](src/promptgrimoire/pages/auth.py)

All error paths return result objects but never log failures. This makes production debugging impossible.

**Examples:**
- `client.py:81-85`: StytchError caught, returned as SendResult, no log
- `auth.py:171-173`: Auth failure shown to user but not logged server-side

**Fix:** Add structured logging:

```python
import logging

logger = logging.getLogger(__name__)

# In client.py
except StytchError as e:
    logger.warning(
        "Magic link send failed",
        extra={"email": email, "error_type": e.details.error_type}
    )
    return SendResult(success=False, error=e.details.error_type)
```

---

### H4. Hardcoded Fallback Values in Pages

**File:** [auth.py:102](src/promptgrimoire/pages/auth.py#L102), [auth.py:127-128](src/promptgrimoire/pages/auth.py#L127-L128)

```python
organization_id=config.default_org_id or "default-org",  # Line 102
connection_id=config.sso_connection_id or "default-connection",  # Line 127
public_token=config.public_token or "default-public-token",  # Line 128
```

These fallbacks are misleading. In production, these would cause cryptic Stytch errors like "organization not found" instead of clear configuration errors.

**Fix:** Either:
1. Fail fast with a clear error if not configured
2. Make these constants with clear names at module level

```python
# Option 1: Fail fast
async def send_magic_link() -> None:
    config = get_config()
    if not config.default_org_id:
        ui.notify("Organization not configured", type="negative")
        logger.error("STYTCH_DEFAULT_ORG_ID not set")
        return
    ...

# Option 2: Named constants (less preferred - still hides config issues)
_FALLBACK_ORG_ID = "default-org"  # Only for dev/mock mode
```

---

## Medium Priority Issues

### M1. Arbitrary Timer Values

**File:** [auth.py:151](src/promptgrimoire/pages/auth.py#L151), [auth.py:173](src/promptgrimoire/pages/auth.py#L173), [auth.py:184](src/promptgrimoire/pages/auth.py#L184), [auth.py:205](src/promptgrimoire/pages/auth.py#L205)

```python
ui.timer(0.5, lambda: ui.navigate.to("/login"), once=True)
```

Magic number `0.5` appears four times. Should be a constant with documentation explaining why.

```python
# Time to display error message before redirecting (seconds)
_ERROR_DISPLAY_SECONDS = 0.5
```

---

### M2. Mock Client Returns Different Roles for Magic Link vs SSO

**File:** [mock.py:103](src/promptgrimoire/auth/mock.py#L103) vs [mock.py:127](src/promptgrimoire/auth/mock.py#L127)

```python
# Magic link returns:
roles=["stytch_member"]

# SSO returns:
roles=["stytch_member", "instructor"]
```

This inconsistency may be intentional (SSO users are instructors) but is undocumented. Add a comment explaining this design decision.

---

### M3. Test Email Hardcoded Instead of Using Constants

**File:** [test_auth_pages.py:41](tests/e2e/test_auth_pages.py#L41), [test_auth_pages.py:52](tests/e2e/test_auth_pages.py#L52)

```python
page.get_by_test_id("email-input").fill("test@example.com")  # Should use constant
page.get_by_test_id("email-input").fill("invalid@nowhere.com")
```

Should import from mock:
```python
from promptgrimoire.auth.mock import MOCK_VALID_EMAILS

# Use a valid email from the constant
valid_email = next(iter(MOCK_VALID_EMAILS))
```

---

### M4. E2E Tests Don't Verify /logout Endpoint

**File:** [auth.py:245-249](src/promptgrimoire/pages/auth.py#L245-L249)

The `/logout` page exists but has no E2E test. The tests only verify the logout button on `/protected`.

---

### M5. conftest.py Duplicates Storage Secret

**File:** [conftest.py:40](tests/conftest.py#L40), [conftest.py:47](tests/conftest.py#L47)

```python
os.environ['STORAGE_SECRET'] = 'test-secret-for-e2e'  # Line 40
ui.run(..., storage_secret='test-secret-for-e2e')  # Line 47
```

Same secret defined twice. Extract to constant.

---

## Test Quality Assessment

### What's Tested Well
- Happy paths for all auth methods
- Error handling for invalid tokens
- Session persistence across navigation
- Protected route access control
- Mock client provides test helpers (`get_sent_magic_links`)

### What's Missing

| Scenario | File | Status |
|----------|------|--------|
| Empty roles list | test_auth_client.py | Missing |
| Multiple roles | test_auth_client.py | Missing |
| Network timeout errors | test_auth_client.py | Missing |
| Sign-up flow E2E (member_created=True) | test_auth_pages.py | Missing |
| Multi-user session isolation | test_auth_pages.py | Missing |
| /logout endpoint | test_auth_pages.py | Missing |
| SSO start redirect actually works | test_auth_pages.py | Broken |
| Session validation on protected routes | test_auth_pages.py | N/A (not implemented) |

---

## Checklist: Fix Before Merge

- [ ] Extract `_extract_roles()` helper and fix empty list crash (C1)
- [ ] Add unit tests for role extraction edge cases (C1)
- [ ] Fix SSO E2E test to actually verify redirect (C2)
- [ ] Move `mock_stytch_client` fixture to conftest.py (H1)
- [ ] Add logging to auth failure paths (H3)
- [ ] Replace hardcoded fallbacks with fail-fast or constants (H4)

## Checklist: Fix Before Production

- [ ] Add session validation on protected routes (H2)
- [ ] Add rate limiting to magic link send endpoint
- [ ] Add audit logging for auth events (who logged in when)
- [ ] Extract timer constant (M1)
- [ ] Document mock role differences (M2)
- [ ] Use MOCK_VALID_EMAILS constant in E2E tests (M3)
- [ ] Add /logout E2E test (M4)
- [ ] Extract storage secret to constant (M5)

---

## Verification Steps

After implementing fixes:

1. **Run unit tests with coverage:**
   ```bash
   uv run pytest tests/unit/test_auth_client.py tests/unit/test_mock_client.py -v --cov=promptgrimoire.auth
   ```

2. **Run E2E tests:**
   ```bash
   uv run pytest tests/e2e/test_auth_pages.py -v
   ```

3. **Verify role extraction edge cases manually:**
   ```python
   # In Python REPL
   from promptgrimoire.auth.client import _extract_roles
   assert _extract_roles([]) == []
   assert _extract_roles(None) == []
   assert _extract_roles(["admin"]) == ["admin"]
   ```

4. **Test SSO redirect in browser:**
   - Start app with `AUTH_MOCK=true`
   - Click "Login with AAF"
   - Verify console shows navigation attempt to mock.stytch.com

---

## Notes for Future Work

1. **MFA Support**: The `mfa_required` error is detected but not handled in the UI. When MFA is needed, the intermediate_session_token should be captured and used in a follow-up MFA verification flow.

2. **Session Refresh**: Currently using 7-day session tokens. Consider implementing session refresh before expiry to avoid forcing re-login.

3. **RBAC Integration**: Roles are stored in session but not used for authorization. When building protected features, add role-checking decorators:
   ```python
   @require_role("instructor")
   @ui.page("/admin")
   async def admin_page():
       ...
   ```

4. **Invite Flow**: The Stytch B2B `magic_links.email.invite()` endpoint is not implemented. This would allow instructors to pre-provision students with specific roles.
