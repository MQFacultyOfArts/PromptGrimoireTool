"""E2E tests for authentication pages.

These tests use MockAuthClient (AUTH_MOCK=true) to test
the auth flow without making real Stytch API calls.
All tests use fresh_page fixture for proper isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from promptgrimoire.auth.mock import (
    MOCK_VALID_MAGIC_TOKEN,
    MOCK_VALID_SSO_TOKEN,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TestLoginPage:
    """Tests for the /login page."""

    def test_login_page_renders(self, fresh_page: Page, app_server: str):
        """Login page displays email input and SSO button."""
        fresh_page.goto(f"{app_server}/login")

        # Should show email input for magic link
        expect(fresh_page.get_by_test_id("email-input")).to_be_visible()
        expect(fresh_page.get_by_test_id("send-magic-link-btn")).to_be_visible()

        # Should show SSO option
        expect(fresh_page.get_by_test_id("sso-login-btn")).to_be_visible()

    def test_magic_link_send_success(self, fresh_page: Page, app_server: str):
        """Submitting valid email shows success message."""
        fresh_page.goto(f"{app_server}/login")

        # Fill in a valid test email
        fresh_page.get_by_test_id("email-input").fill("test@example.com")
        fresh_page.get_by_test_id("send-magic-link-btn").click()

        # Should show success message
        expect(fresh_page.get_by_text("Magic link sent")).to_be_visible()

    def test_magic_link_send_invalid_email(self, fresh_page: Page, app_server: str):
        """Submitting invalid email shows error message."""
        fresh_page.goto(f"{app_server}/login")

        # Fill in an invalid email (not in MOCK_VALID_EMAILS)
        fresh_page.get_by_test_id("email-input").fill("invalid@nowhere.com")
        fresh_page.get_by_test_id("send-magic-link-btn").click()

        # Should show error message
        expect(fresh_page.get_by_text("invalid_email")).to_be_visible()


class TestMagicLinkCallback:
    """Tests for the /auth/callback page (magic link authentication)."""

    def test_callback_with_valid_token(self, fresh_page: Page, app_server: str):
        """Valid token authenticates and redirects to index page."""
        # Navigate to callback with valid mock token
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")

        # Should redirect to index page after successful auth
        expect(fresh_page).to_have_url(f"{app_server}/")

    def test_callback_with_invalid_token(self, fresh_page: Page, app_server: str):
        """Invalid token shows error and redirects to login."""
        fresh_page.goto(f"{app_server}/auth/callback?token=bad-token")

        # Should show error first (in label or notification)
        expect(fresh_page.get_by_text("Error: invalid_token")).to_be_visible()

        # Then redirect back to login (wait for timer)
        expect(fresh_page).to_have_url(f"{app_server}/login", timeout=3000)

    def test_callback_without_token(self, fresh_page: Page, app_server: str):
        """Missing token redirects to login."""
        fresh_page.goto(f"{app_server}/auth/callback")

        # Should show error message (use first() since text appears in label and toast)
        expect(fresh_page.get_by_text("Invalid or missing token").first).to_be_visible()

        # Then redirect to login (wait for timer)
        expect(fresh_page).to_have_url(f"{app_server}/login", timeout=3000)


class TestSSOFlow:
    """Tests for SSO authentication flow."""

    def test_sso_start_redirects(self, fresh_page: Page, app_server: str):
        """SSO start generates redirect URL with correct parameters."""
        fresh_page.goto(f"{app_server}/login")

        # Capture the redirect URL using route interception
        redirect_url = None

        def capture_redirect(route):
            nonlocal redirect_url
            redirect_url = route.request.url
            route.abort()  # Don't actually navigate to mock.stytch.com

        fresh_page.route("**/mock.stytch.com/**", capture_redirect)
        fresh_page.get_by_test_id("sso-login-btn").click()
        fresh_page.wait_for_timeout(200)  # Give time for navigation to be intercepted

        # Verify the redirect URL was generated correctly
        assert redirect_url is not None, "SSO redirect was not triggered"
        assert "mock.stytch.com" in redirect_url
        assert "connection_id=" in redirect_url
        assert "public_token=" in redirect_url

    def test_sso_callback_with_valid_token(self, fresh_page: Page, app_server: str):
        """Valid SSO token authenticates and redirects."""
        fresh_page.goto(f"{app_server}/auth/sso/callback?token={MOCK_VALID_SSO_TOKEN}")

        # Should redirect to index page after successful auth
        expect(fresh_page).to_have_url(f"{app_server}/")

    def test_sso_callback_with_invalid_token(self, fresh_page: Page, app_server: str):
        """Invalid SSO token shows error."""
        fresh_page.goto(f"{app_server}/auth/sso/callback?token=bad-sso-token")

        # Should show error (use first() since text appears in label and toast)
        expect(fresh_page.get_by_text("invalid_token").first).to_be_visible()

        # Then redirect to login (wait for timer)
        expect(fresh_page).to_have_url(f"{app_server}/login", timeout=3000)


class TestProtectedPage:
    """Tests for the /protected page."""

    def test_protected_requires_auth(self, fresh_page: Page, app_server: str):
        """Protected page redirects to login if not authenticated."""
        fresh_page.goto(f"{app_server}/protected")

        # Should redirect to login
        expect(fresh_page).to_have_url(f"{app_server}/login")

    def test_protected_shows_user_info(self, fresh_page: Page, app_server: str):
        """Protected page shows user info when authenticated."""
        # First authenticate
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(fresh_page).to_have_url(f"{app_server}/")

        # Navigate to protected page
        fresh_page.goto(f"{app_server}/protected")

        # Should show user email and roles
        expect(fresh_page.get_by_text("test@example.com")).to_be_visible()
        expect(fresh_page.get_by_text("stytch_member")).to_be_visible()

    def test_logout_clears_session(self, fresh_page: Page, app_server: str):
        """Logout clears session and redirects to login."""
        # First authenticate
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(fresh_page).to_have_url(f"{app_server}/")

        # Navigate to protected page to get logout button
        fresh_page.goto(f"{app_server}/protected")

        # Click logout
        fresh_page.get_by_test_id("logout-btn").click()

        # Should redirect to login
        expect(fresh_page).to_have_url(f"{app_server}/login")

        # Trying to access protected should redirect
        fresh_page.goto(f"{app_server}/protected")
        expect(fresh_page).to_have_url(f"{app_server}/login")


class TestSessionPersistence:
    """Tests for session persistence across page loads."""

    def test_session_persists_on_refresh(self, fresh_page: Page, app_server: str):
        """Session persists after page refresh."""
        # Authenticate
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(fresh_page).to_have_url(f"{app_server}/")

        # Navigate to protected and refresh
        fresh_page.goto(f"{app_server}/protected")
        fresh_page.reload()

        # Should still be on protected page (not redirected to login)
        expect(fresh_page).to_have_url(f"{app_server}/protected")
        expect(fresh_page.get_by_text("test@example.com")).to_be_visible()

    def test_session_persists_across_navigation(
        self, fresh_page: Page, app_server: str
    ):
        """Session persists when navigating to other pages."""
        # Authenticate
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(fresh_page).to_have_url(f"{app_server}/")

        # Navigate away and back to protected
        fresh_page.goto(f"{app_server}/login")
        fresh_page.goto(f"{app_server}/protected")

        # Should still be authenticated (not redirected to login)
        expect(fresh_page).to_have_url(f"{app_server}/protected")
