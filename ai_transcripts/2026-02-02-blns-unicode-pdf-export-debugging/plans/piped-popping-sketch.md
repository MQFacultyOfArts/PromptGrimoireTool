# Spike 3: Stytch B2B Auth - Magic Links + AAF SSO

## Objective

Validate Stytch B2B authentication with NiceGUI, implementing:
1. **Magic links** - For external users, fallback auth
2. **SSO via AAF Rapid IdP** - Primary auth for university users (SAML)
3. **Mock auth system** - For testing without real Stytch calls

## Acceptance Criteria

- [ ] Magic link: send email, handle callback, create session
- [ ] SSO: start flow, handle SAML callback, create session
- [ ] Session persists across page refreshes
- [ ] Auth can be mocked for integration/E2E tests
- [ ] Clear separation between real and mock auth

---

## Stytch Dashboard Setup

### Step 1: Create B2B Project

1. Go to [Stytch Dashboard](https://stytch.com/dashboard)
2. Create a new **B2B SaaS Authentication** project (not Consumer)
3. Note your credentials:
   - `project_id` (starts with `project-test-` or `project-live-`)
   - `secret` (starts with `secret-test-` or `secret-live-`)
   - `public_token` (for frontend SSO redirects)

### Step 2: Configure Redirect URLs

In Dashboard → **Redirect URLs**:

| URL | Purpose |
|-----|---------|
| `http://localhost:8080/auth/callback` | Magic link callback (dev) |
| `http://localhost:8080/auth/sso/callback` | SSO callback (dev) |
| `https://yourdomain.com/auth/callback` | Magic link callback (prod) |
| `https://yourdomain.com/auth/sso/callback` | SSO callback (prod) |

### Step 3: Enable Auth Methods

In Dashboard → **Authentication** → **Auth methods**:

- [x] **Email Magic Links** - Enable for fallback auth
- [x] **SSO** - Enable for AAF integration

### Step 4: Create Test Organization

For development, create an Organization via API or Dashboard:

```python
# Via API
response = await client.organizations.create_async(
    organization_name="Test Class",
    organization_slug="test-class",
    email_jit_provisioning="ALL_ALLOWED",  # Allow any email to join
    email_invites="ALL_ALLOWED",
)
org_id = response.organization.organization_id
```

Or in Dashboard → **Organizations** → **Create Organization**

### Step 5: Configure AAF SSO Connection (Per Organization)

For each Organization that needs AAF login:

#### 5a. Create SAML Connection in Stytch

```python
response = await client.sso.saml.create_connection_async(
    organization_id=org_id,
    display_name="AAF Login",
    identity_provider="shibboleth"  # AAF uses Shibboleth
)

# Save these for AAF registration
acs_url = response.connection.acs_url
audience_uri = response.connection.audience_uri
connection_id = response.connection.connection_id
```

#### 5b. Register Service with AAF

Contact AAF (support@aaf.edu.au) or use Rapid IdP admin interface:

1. Provide Stytch's **ACS URL** as the Assertion Consumer Service
2. Provide Stytch's **Audience URI** as the Entity ID
3. Request these attributes be released:
   - `mail` (email)
   - `displayName` or `givenName` + `sn`
   - `eduPersonAffiliation` (for role mapping)

#### 5c. Update Stytch with AAF Metadata

Once AAF provides their IdP metadata:

```python
await client.sso.saml.update_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
    idp_entity_id="https://rapid.aaf.edu.au/idp/shibboleth",
    idp_sso_url="https://rapid.aaf.edu.au/idp/profile/SAML2/Redirect/SSO",
    x509_certificate="-----BEGIN CERTIFICATE-----\n...",
    attribute_mapping={
        "email": "mail",
        "first_name": "givenName",
        "last_name": "sn"
    }
)
```

### Step 6: Configure RBAC (Optional for Spike)

In Dashboard → **Authorization** → **RBAC**:

Define custom roles:
- `instructor` - Can create/manage conversations
- `student` - Can read and annotate

Define custom resources:
- `conversations` with actions: create, read, annotate, delete
- `annotations` with actions: create, read, update, delete

### Organization Settings Reference

| Setting | Magic Links | AAF SSO |
|---------|------------|---------|
| `email_jit_provisioning` | `ALL_ALLOWED` or `RESTRICTED` | N/A |
| `email_allowed_domains` | Optional restriction | N/A |
| `sso_jit_provisioning` | N/A | `ALL_ALLOWED` |
| `allowed_auth_methods` | Include `magic_links` | Include `sso` |

---

## Architecture

### Auth Strategy

```
┌─────────────────────────────────────────────────────┐
│                    /login                            │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Magic Link   │          │ SSO (AAF)        │     │
│  │ Email input  │          │ "Login with AAF" │     │
│  └──────┬───────┘          └────────┬─────────┘     │
│         │                           │               │
│         ▼                           ▼               │
│  /auth/callback?token=xxx    /auth/sso/callback     │
│         │                           │               │
│         └───────────┬───────────────┘               │
│                     ▼                               │
│              Session Created                        │
│              app.storage.user                       │
└─────────────────────────────────────────────────────┘
```

### Why B2B

- **Organization** = Class (multi-tenancy)
- **Member** = Student/Instructor
- **SSO Connection** = AAF Rapid IdP per organization
- **RBAC** = Built-in role management

---

## Testing Strategy

### Three-Layer Approach

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: Unit Tests                                 │
│ - Mock stytch.B2BClient entirely                    │
│ - Test our wrapper logic in isolation               │
│ - Fast, no network calls                            │
└─────────────────────────────────────────────────────┘
                        │
┌─────────────────────────────────────────────────────┐
│ Layer 2: Integration Tests (Mock Auth)              │
│ - Use MockAuthClient instead of real Stytch         │
│ - Test full auth flow with predictable responses    │
│ - E2E browser tests with mocked backend             │
└─────────────────────────────────────────────────────┘
                        │
┌─────────────────────────────────────────────────────┐
│ Layer 3: Sandbox Tests (Real Stytch API)            │
│ - Use Stytch sandbox tokens                         │
│ - Validate real API integration works               │
│ - Run separately, may be slower                     │
└─────────────────────────────────────────────────────┘
```

### Mock Auth Client

```python
# src/promptgrimoire/auth/mock.py

class MockAuthClient:
    """Drop-in replacement for StytchB2BClient in tests."""

    # Predictable test users
    VALID_EMAILS = {"test@example.com", "student@uni.edu"}
    VALID_TOKEN = "mock-valid-token"
    VALID_SESSION = "mock-session-token"

    async def send_magic_link(self, email, org_id, callback_url):
        if email in self.VALID_EMAILS:
            return SendResult(success=True, user_id="mock-user-123")
        return SendResult(success=False, error="invalid_email")

    async def authenticate_token(self, token):
        if token == self.VALID_TOKEN:
            return AuthResult(
                success=True,
                session_token=self.VALID_SESSION,
                member_id="mock-member-123",
                email="test@example.com"
            )
        return AuthResult(success=False, error="invalid_token")

    async def authenticate_sso(self, token):
        # Similar pattern for SSO tokens
        ...
```

### Auth Client Factory

```python
# src/promptgrimoire/auth/factory.py

def get_auth_client() -> AuthClientProtocol:
    """Return appropriate auth client based on environment."""
    if os.environ.get("AUTH_MOCK") == "true":
        from promptgrimoire.auth.mock import MockAuthClient
        return MockAuthClient()
    else:
        from promptgrimoire.auth.client import StytchB2BClient
        config = AuthConfig.from_env()
        return StytchB2BClient(config.project_id, config.secret)
```

### Test Configuration

```python
# tests/conftest.py

# For E2E tests with mock auth
_SERVER_SCRIPT = """
import os
os.environ['AUTH_MOCK'] = 'true'  # Use MockAuthClient
os.environ['STORAGE_SECRET'] = 'test-secret'
# ... rest of server setup
"""

# For sandbox tests (real Stytch API)
@pytest.fixture
def sandbox_auth():
    """Use real Stytch with sandbox credentials."""
    os.environ['AUTH_MOCK'] = 'false'
    os.environ['STYTCH_PROJECT_ID'] = 'project-test-xxx'
    os.environ['STYTCH_SECRET'] = 'secret-test-xxx'
```

---

## Implementation Plan

### Phase 1: Auth Module with Mock Support

#### 1. `src/promptgrimoire/auth/protocol.py`

```python
from typing import Protocol

class AuthClientProtocol(Protocol):
    async def send_magic_link(self, email: str, org_id: str, callback_url: str) -> SendResult: ...
    async def authenticate_magic_link(self, token: str) -> AuthResult: ...
    async def start_sso(self, org_id: str, connection_id: str) -> SSOStartResult: ...
    async def authenticate_sso(self, token: str) -> AuthResult: ...
    async def validate_session(self, session_token: str) -> SessionResult: ...
```

#### 2. `src/promptgrimoire/auth/client.py`

Real Stytch B2B implementation.

#### 3. `src/promptgrimoire/auth/mock.py`

Mock implementation for testing.

#### 4. `src/promptgrimoire/auth/factory.py`

Factory function to get appropriate client.

### Phase 2: NiceGUI Pages

#### 5. `src/promptgrimoire/pages/auth.py`

Routes:
- `/login` - Email input + "Login with AAF" button
- `/auth/callback` - Magic link token handler
- `/auth/sso/start` - Redirect to AAF
- `/auth/sso/callback` - SAML assertion handler
- `/protected` - Demo protected page
- `/logout` - Clear session

### Phase 3: SSO Configuration

#### 6. `src/promptgrimoire/auth/sso.py`

SSO connection management:
- Create SAML connection for AAF
- Store connection_id per organization
- Handle attribute mapping (eduPersonAffiliation → roles)

---

## File Structure

```
src/promptgrimoire/
├── __init__.py
├── auth/
│   ├── __init__.py       # Exports
│   ├── protocol.py       # AuthClientProtocol
│   ├── client.py         # StytchB2BClient (real)
│   ├── mock.py           # MockAuthClient (testing)
│   ├── factory.py        # get_auth_client()
│   ├── config.py         # AuthConfig
│   ├── models.py         # SendResult, AuthResult, etc.
│   └── sso.py            # SSO connection helpers
└── pages/
    └── auth.py           # All auth routes

tests/
├── conftest.py           # Updated with mock/sandbox fixtures
├── unit/
│   ├── test_auth_client.py    # Real client with mocked Stytch
│   └── test_mock_client.py    # Mock client behavior
├── integration/
│   └── test_auth_flow.py      # Full flow with mock
└── e2e/
    ├── test_auth_mock.py      # E2E with MockAuthClient
    └── test_auth_sandbox.py   # E2E with Stytch sandbox
```

---

## SSO Flow for AAF Rapid IdP

### 1. Create SAML Connection (One-time setup)

```python
# Create connection in Stytch
response = await client.sso.saml.create_connection_async(
    organization_id=org_id,
    display_name="AAF Login",
    identity_provider="shibboleth"
)

# Get ACS URL and Audience URI for AAF registration
acs_url = response.connection.acs_url
audience_uri = response.connection.audience_uri

# After AAF provides metadata, update connection
await client.sso.saml.update_connection_async(
    organization_id=org_id,
    connection_id=connection_id,
    idp_entity_id="https://rapid.aaf.edu.au/idp/shibboleth",
    idp_sso_url="https://rapid.aaf.edu.au/idp/profile/SAML2/Redirect/SSO",
    x509_certificate="-----BEGIN CERTIFICATE-----...",
    attribute_mapping={
        "email": "mail",
        "first_name": "givenName",
        "last_name": "sn"
    }
)
```

### 2. Start SSO Flow

```python
@ui.page("/auth/sso/start")
async def sso_start(request):
    org_id = request.query_params.get("org_id")
    connection_id = get_sso_connection_for_org(org_id)

    # Redirect to Stytch SSO start endpoint
    sso_url = (
        f"https://test.stytch.com/v1/b2b/sso/start"
        f"?connection_id={connection_id}"
        f"&public_token={PUBLIC_TOKEN}"
    )
    return RedirectResponse(sso_url)
```

### 3. Handle SSO Callback

```python
@ui.page("/auth/sso/callback")
async def sso_callback(request):
    token = request.query_params.get("token")

    auth_client = get_auth_client()
    result = await auth_client.authenticate_sso(token)

    if result.success:
        app.storage.user["session_token"] = result.session_token
        app.storage.user["member_id"] = result.member_id
        ui.navigate.to("/protected")
    else:
        ui.notify(f"SSO failed: {result.error}", type="negative")
```

---

## Test Cases

### Unit Tests (Mocked Stytch)

```python
class TestStytchB2BClient:
    async def test_send_magic_link_success(self, mock_stytch):
        ...
    async def test_authenticate_magic_link_success(self, mock_stytch):
        ...
    async def test_authenticate_sso_success(self, mock_stytch):
        ...
```

### Integration Tests (MockAuthClient)

```python
class TestAuthFlowWithMock:
    async def test_magic_link_full_flow(self):
        """Send link → callback → session created."""
        ...
    async def test_sso_full_flow(self):
        """Start SSO → callback → session created."""
        ...
```

### E2E Tests (MockAuthClient)

```python
class TestLoginPageE2E:
    def test_login_renders_both_options(self, page, app_server):
        """Shows email input AND 'Login with AAF' button."""
        page.goto(f"{app_server}/login")
        expect(page.get_by_test_id("email-input")).to_be_visible()
        expect(page.get_by_test_id("sso-button")).to_be_visible()

    def test_magic_link_flow(self, page, app_server):
        """Complete magic link auth with mock."""
        page.goto(f"{app_server}/login")
        page.get_by_test_id("email-input").fill("test@example.com")
        page.get_by_test_id("send-btn").click()

        # Navigate to callback with mock token
        page.goto(f"{app_server}/auth/callback?token=mock-valid-token")
        expect(page).to_have_url(f"{app_server}/protected")
```

### Sandbox Tests (Real Stytch)

```python
@pytest.mark.sandbox
class TestStytchSandbox:
    def test_magic_link_with_sandbox_token(self, page, sandbox_server):
        """Use real Stytch sandbox token."""
        token = "DOYoip3rvIMMW5lgItikFK-Ak1CfMsgjuiCyI7uuU94="
        page.goto(f"{sandbox_server}/auth/callback?token={token}")
        expect(page).to_have_url(f"{sandbox_server}/protected")
```

---

## Environment Variables

```bash
# .env.development
STYTCH_PROJECT_ID=project-test-xxx
STYTCH_SECRET=secret-test-xxx
BASE_URL=http://localhost:8080
STORAGE_SECRET=dev-secret-change-in-prod
AUTH_MOCK=false

# .env.test (for E2E with mock)
AUTH_MOCK=true
STORAGE_SECRET=test-secret

# .env.sandbox (for Stytch sandbox tests)
AUTH_MOCK=false
STYTCH_PROJECT_ID=project-test-xxx
STYTCH_SECRET=secret-test-xxx
```

---

## Verification

### 1. Unit Tests

```bash
uv run pytest tests/unit/test_auth_client.py -v
uv run pytest tests/unit/test_mock_client.py -v
```

### 2. E2E Tests (Mock)

```bash
uv run pytest tests/e2e/test_auth_mock.py -v
```

### 3. Sandbox Tests

```bash
uv run pytest tests/e2e/test_auth_sandbox.py -v -m sandbox
```

### 4. Manual Testing

1. Start app: `AUTH_MOCK=true uv run python -m promptgrimoire`
2. Navigate to `/login`
3. Test magic link with `test@example.com`
4. Test callback with `?token=mock-valid-token`
5. Verify session persists on refresh

---

## Cached Documentation

- [docs/stytch/b2b-basics.md](docs/stytch/b2b-basics.md) - Organizations, Members, settings, core flows
- [docs/stytch/b2b-overview.md](docs/stytch/b2b-overview.md) - Core concepts
- [docs/stytch/b2b-quickstart.md](docs/stytch/b2b-quickstart.md) - Python SDK setup
- [docs/stytch/b2b-magic-links.md](docs/stytch/b2b-magic-links.md) - Magic link API
- [docs/stytch/b2b-authenticate.md](docs/stytch/b2b-authenticate.md) - Token auth
- [docs/stytch/sso-overview.md](docs/stytch/sso-overview.md) - SSO setup guide
- [docs/stytch/sso-saml.md](docs/stytch/sso-saml.md) - SAML/AAF setup
- [docs/stytch/rbac-guide.md](docs/stytch/rbac-guide.md) - Roles and permissions
- [docs/stytch/testing.md](docs/stytch/testing.md) - Sandbox values, E2E patterns
- [docs/aaf/rapid-idp.md](docs/aaf/rapid-idp.md) - AAF Rapid IdP details
