# AAF OIDC Authentication — Phase 3: Google OAuth

**Goal:** Add Google OAuth as a backstop login method for MQ students

**Architecture:** Copy the existing GitHub OAuth UI pattern for Google (provider-agnostic `get_oauth_start_url()` already handles any provider), genericise the OAuth callback messages, reorder login page buttons to match institutional hierarchy

**Tech Stack:** Python 3.14, NiceGUI, Stytch B2B OAuth

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-02-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### aaf-oidc-auth-188-189.AC2: Google OAuth login works end-to-end
- **aaf-oidc-auth-188-189.AC2.1 Success:** Student with @students.mq.edu.au Google account clicks "Login with Google", authenticates, auto-provisions into app
- **aaf-oidc-auth-188-189.AC2.2 Success:** "Login with Google" button appears on login page below AAF button
- **aaf-oidc-auth-188-189.AC2.3 Success:** OAuth callback handler works identically for Google and GitHub providers
- **aaf-oidc-auth-188-189.AC2.4 Failure:** Google OAuth error redirects to login page with error message

### aaf-oidc-auth-188-189.AC3: JIT provisioning
- **aaf-oidc-auth-188-189.AC3.2 Success:** First-time Google OAuth user with @students.mq.edu.au auto-creates local account
- **aaf-oidc-auth-188-189.AC3.3 Edge:** JIT provisioning bootstrap — at least one member with verified @students.mq.edu.au email exists before student JIT works

---

## Key Files Reference

| File | Role |
|------|------|
| `src/promptgrimoire/pages/auth.py:319-363` | `_build_github_oauth_section()` — pattern to copy for Google |
| `src/promptgrimoire/pages/auth.py:395-417` | Login page layout — reorder buttons |
| `src/promptgrimoire/pages/auth.py:525-574` | OAuth callback — genericise hardcoded "GitHub" strings |
| `src/promptgrimoire/auth/client.py:269-302` | `get_oauth_start_url()` — already provider-agnostic, no changes needed |
| `src/promptgrimoire/auth/mock.py:253-284` | Mock OAuth — already provider-agnostic |
| `CLAUDE.md` | Project conventions |

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `_build_google_oauth_section()` function

**Verifies:** aaf-oidc-auth-188-189.AC2.2

**Files:**
- Modify: `src/promptgrimoire/pages/auth.py` — add new function after `_build_github_oauth_section()`

**Implementation:**

Create `_build_google_oauth_section()` following the exact pattern of `_build_github_oauth_section()` (lines 319-363):

```python
def _build_google_oauth_section() -> None:
    """Build the Google OAuth login section."""
    with ui.card().classes("w-96 p-4"):
        ui.label("Google Login").classes("text-lg font-semibold mb-2")

        def start_google_oauth() -> None:
            logger.info("Google OAuth login button clicked")
            auth_client = get_auth_client()
            settings = get_settings()

            if not settings.stytch.public_token:
                logger.error("STYTCH__PUBLIC_TOKEN not configured")
                ui.notify("Google login not configured", type="negative")
                return

            if not settings.stytch.default_org_id:
                logger.error("STYTCH__DEFAULT_ORG_ID not configured")
                ui.notify("Google login not configured", type="negative")
                return

            callback_url = f"{settings.app.base_url}/auth/oauth/callback"
            logger.info(
                "Starting Google OAuth: org_id=%s, callback=%s",
                settings.stytch.default_org_id,
                callback_url,
            )

            result = auth_client.get_oauth_start_url(
                provider="google",
                public_token=settings.stytch.public_token,
                organization_id=settings.stytch.default_org_id,
                login_redirect_url=callback_url,
            )

            if result.success and result.redirect_url:
                logger.info("Google OAuth redirect URL: %s", result.redirect_url)
                ui.navigate.to(result.redirect_url)
            else:
                logger.warning("Google OAuth start failed: %s", result.error)
                ui.notify(f"Google login error: {result.error}", type="negative")

        ui.button(
            "Login with Google",
            on_click=start_google_oauth,
        ).props('data-testid="google-login-btn"').classes("w-full")
```

The only differences from GitHub: provider string is `"google"`, label says "Google", data-testid is `"google-login-btn"`.

**Verification:**

```bash
uv run test-all
```

Expected: All tests pass. New function doesn't break anything (not yet called from login page).

**Commit:** `feat(auth): add Google OAuth login section`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Genericise OAuth callback and reorder login page

**Verifies:** aaf-oidc-auth-188-189.AC2.3, aaf-oidc-auth-188-189.AC2.4

**Files:**
- Modify: `src/promptgrimoire/pages/auth.py:525-574` — genericise OAuth callback
- Modify: `src/promptgrimoire/pages/auth.py:395-417` — reorder login page layout
- Test: `tests/unit/` or `tests/e2e/` — verify button ordering and callback behaviour

**Implementation:**

**Part A: Genericise OAuth callback** (lines 525-574)

**Pre-step: Audit `auth_method` usages.** Before changing `auth_method` from `"github"` to `"oauth"`, search the codebase for all references to `auth_method="github"` or the string `"github"` in auth-related code:

```bash
uv run rg 'auth_method.*github\|"github"' src/ tests/
```

If any code branches on `auth_method == "github"` (e.g., for provider-specific session logic or analytics), those branches must be updated to handle `"oauth"` or refactored to be provider-agnostic. If no code branches on the specific value, the change is safe.

Change the hardcoded GitHub strings to generic OAuth:

1. Log message: `"OAuth callback received (GitHub)"` → `"OAuth callback received"`
2. UI label: `"Processing GitHub login..."` → `"Processing login..."`
3. `auth_method`: `"github"` → `"oauth"`
4. Error notify: `"GitHub authentication failed: ..."` → `"OAuth authentication failed: ..."`

**Part B: Reorder login page** (lines 395-417)

Reorder to match design hierarchy — AAF primary, Google secondary, magic link tertiary, GitHub small:

```python
@ui.page("/login")
async def login_page() -> None:
    """Login page with AAF SSO, Google OAuth, magic link, and GitHub OAuth options."""
    user = _get_session_user()
    if user:
        ui.navigate.to("/")
        return

    ui.add_body_html(_BROWSER_GATE_JS)
    ui.label("Login to PromptGrimoire").classes("text-2xl font-bold mb-4")

    if get_settings().dev.auth_mock:
        _build_mock_login_section()
        ui.label("— or —").classes("my-4")

    _build_sso_section()          # AAF (primary)
    ui.label("— or —").classes("my-4")
    _build_google_oauth_section()  # Google (backstop)
    ui.label("— or —").classes("my-4")
    _build_magic_link_section()    # Magic link (back-backstop)
    ui.label("— or —").classes("my-4")
    _build_github_oauth_section()  # GitHub (dev/admin)
```

**Testing:**

Tests must verify:
- aaf-oidc-auth-188-189.AC2.3: OAuth callback uses generic `auth_method="oauth"` (works for both Google and GitHub tokens)
- aaf-oidc-auth-188-189.AC2.4: OAuth error returns to login page with error message (existing test may cover this)

**Verification:**

```bash
uv run test-all
```

Expected: All tests pass. E2E tests that check for "GitHub" text in OAuth callback may need updating.

**Commit:** `feat(auth): genericise OAuth callback and reorder login page for AAF priority`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Configure Stytch Google OAuth and JIT provisioning (dashboard)

**Verifies:** aaf-oidc-auth-188-189.AC2.1, aaf-oidc-auth-188-189.AC3.2, aaf-oidc-auth-188-189.AC3.3

**This is a manual/infrastructure task. No code changes.**

**Prerequisites:** This task requires access to Google Cloud Console to create OAuth 2.0 credentials. If Google Cloud access is not available, Tasks 1-2 (code changes) can still be completed and merged — the Google OAuth button will appear but redirect will fail until dashboard config is done. This task can be deferred without blocking the code phase.

**Step 1: Enable Google OAuth in Stytch**

In the Stytch B2B dashboard:
1. Navigate to Authentication > OAuth
2. Enable Google as an OAuth provider
3. Configure Google Cloud OAuth credentials:
   - Create OAuth 2.0 client in Google Cloud Console
   - Set authorized redirect URI to Stytch's OAuth callback URL
   - Copy client ID and secret to Stytch dashboard

**Step 2: Configure JIT provisioning**

In the Stytch B2B dashboard, for the organization:
1. Set `email_jit_provisioning` to `RESTRICTED`
2. Add to `email_allowed_domains`:
   - `mq.edu.au`
   - `students.mq.edu.au`

**Step 3: Bootstrap JIT provisioning**

JIT provisioning requires at least one existing member with a verified email from each allowed domain. Create a member manually:
1. Send a magic link to a `@students.mq.edu.au` email address
2. Authenticate via the magic link to create the first member
3. After this, Google OAuth JIT works for `@students.mq.edu.au` students

**Verification:**

1. Log in with a Google account that uses `@students.mq.edu.au`
2. First-time user should be auto-provisioned (no pre-invitation needed)
3. User should land in the app with an active session

<!-- END_TASK_3 -->

---

## Phase Completion Criteria

Phase 3 is complete when:
1. "Login with Google" button appears on login page below AAF button (Task 1)
2. OAuth callback is provider-agnostic (Task 2)
3. Login page order: AAF → Google → Magic Link → GitHub (Task 2)
4. Stytch Google OAuth enabled and JIT provisioning configured (Task 3)
5. `uv run test-all` passes with zero failures
