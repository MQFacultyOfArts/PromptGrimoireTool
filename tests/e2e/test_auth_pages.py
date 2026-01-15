"""E2E tests for authentication pages.

These tests use MockAuthClient (AUTH_MOCK=true) to test
the auth flow without making real Stytch API calls.
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

    def test_login_page_renders(self, page: Page, app_server: str):
        """Login page displays email input and SSO button."""
        page.goto(f"{app_server}/login")

        # Should show email input for magic link
        expect(page.get_by_test_id("email-input")).to_be_visible()
        expect(page.get_by_test_id("send-magic-link-btn")).to_be_visible()

        # Should show SSO option
        expect(page.get_by_test_id("sso-login-btn")).to_be_visible()

    def test_magic_link_send_success(self, page: Page, app_server: str):
        """Submitting valid email shows success message."""
        page.goto(f"{app_server}/login")

        # Fill in a valid test email
        page.get_by_test_id("email-input").fill("test@example.com")
        page.get_by_test_id("send-magic-link-btn").click()

        # Should show success message
        expect(page.get_by_text("Magic link sent")).to_be_visible()

    def test_magic_link_send_invalid_email(self, page: Page, app_server: str):
        """Submitting invalid email shows error message."""
        page.goto(f"{app_server}/login")

        # Fill in an invalid email (not in MOCK_VALID_EMAILS)
        page.get_by_test_id("email-input").fill("invalid@nowhere.com")
        page.get_by_test_id("send-magic-link-btn").click()

        # Should show error message
        expect(page.get_by_text("invalid_email")).to_be_visible()


class TestMagicLinkCallback:
    """Tests for the /auth/callback page (magic link authentication)."""

    def test_callback_with_valid_token(self, page: Page, app_server: str):
        """Valid token authenticates and redirects to protected page."""
        # Navigate to callback with valid mock token
        page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")

        # Should redirect to protected page
        expect(page).to_have_url(f"{app_server}/protected")

        # Should show authenticated content
        expect(page.get_by_text("test@example.com")).to_be_visible()

    def test_callback_with_invalid_token(self, page: Page, app_server: str):
        """Invalid token shows error and redirects to login."""
        page.goto(f"{app_server}/auth/callback?token=bad-token")

        # Should show error first (in label or notification)
        expect(page.get_by_text("Error: invalid_token")).to_be_visible()

        # Then redirect back to login (wait for timer)
        expect(page).to_have_url(f"{app_server}/login", timeout=3000)

    def test_callback_without_token(self, page: Page, app_server: str):
        """Missing token redirects to login."""
        page.goto(f"{app_server}/auth/callback")

        # Should show error message (use first() since text appears in label and toast)
        expect(page.get_by_text("No token provided").first).to_be_visible()

        # Then redirect to login (wait for timer)
        expect(page).to_have_url(f"{app_server}/login", timeout=3000)


class TestSSOFlow:
    """Tests for SSO authentication flow."""

    def test_sso_start_redirects(self, page: Page, app_server: str):
        """SSO start generates redirect URL with correct parameters."""
        page.goto(f"{app_server}/login")

        # Capture the redirect URL using route interception
        redirect_url = None

        def capture_redirect(route):
            nonlocal redirect_url
            redirect_url = route.request.url
            route.abort()  # Don't actually navigate to mock.stytch.com

        page.route("**/mock.stytch.com/**", capture_redirect)
        page.get_by_test_id("sso-login-btn").click()
        page.wait_for_timeout(200)  # Give time for navigation to be intercepted

        # Verify the redirect URL was generated correctly
        assert redirect_url is not None, "SSO redirect was not triggered"
        assert "mock.stytch.com" in redirect_url
        assert "connection_id=" in redirect_url
        assert "public_token=" in redirect_url

    def test_sso_callback_with_valid_token(self, page: Page, app_server: str):
        """Valid SSO token authenticates and redirects."""
        page.goto(f"{app_server}/auth/sso/callback?token={MOCK_VALID_SSO_TOKEN}")

        # Should redirect to protected page
        expect(page).to_have_url(f"{app_server}/protected")

        # Should show SSO user's email
        expect(page.get_by_text("aaf-user@uni.edu")).to_be_visible()

    def test_sso_callback_with_invalid_token(self, page: Page, app_server: str):
        """Invalid SSO token shows error."""
        page.goto(f"{app_server}/auth/sso/callback?token=bad-sso-token")

        # Should show error (use first() since text appears in label and toast)
        expect(page.get_by_text("invalid_token").first).to_be_visible()

        # Then redirect to login (wait for timer)
        expect(page).to_have_url(f"{app_server}/login", timeout=3000)


class TestProtectedPage:
    """Tests for the /protected page."""

    def test_protected_requires_auth(self, page: Page, app_server: str):
        """Protected page redirects to login if not authenticated."""
        page.goto(f"{app_server}/protected")

        # Should redirect to login
        expect(page).to_have_url(f"{app_server}/login")

    def test_protected_shows_user_info(self, page: Page, app_server: str):
        """Protected page shows user info when authenticated."""
        # First authenticate
        page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(page).to_have_url(f"{app_server}/protected")

        # Should show user email and roles
        expect(page.get_by_text("test@example.com")).to_be_visible()
        expect(page.get_by_text("stytch_member")).to_be_visible()

    def test_logout_clears_session(self, page: Page, app_server: str):
        """Logout clears session and redirects to login."""
        # First authenticate
        page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(page).to_have_url(f"{app_server}/protected")

        # Click logout
        page.get_by_test_id("logout-btn").click()

        # Should redirect to login
        expect(page).to_have_url(f"{app_server}/login")

        # Trying to access protected should redirect
        page.goto(f"{app_server}/protected")
        expect(page).to_have_url(f"{app_server}/login")


class TestSessionPersistence:
    """Tests for session persistence across page loads."""

    def test_session_persists_on_refresh(self, page: Page, app_server: str):
        """Session persists after page refresh."""
        # Authenticate
        page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(page).to_have_url(f"{app_server}/protected")

        # Refresh the page
        page.reload()

        # Should still be on protected page
        expect(page).to_have_url(f"{app_server}/protected")
        expect(page.get_by_text("test@example.com")).to_be_visible()

    def test_session_persists_across_navigation(self, page: Page, app_server: str):
        """Session persists when navigating to other pages."""
        # Authenticate
        page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(page).to_have_url(f"{app_server}/protected")

        # Navigate away and back
        page.goto(f"{app_server}/login")
        page.goto(f"{app_server}/protected")

        # Should still be authenticated
        expect(page).to_have_url(f"{app_server}/protected")
