"""E2E tests for authentication pages.

These tests use MockAuthClient (AUTH_MOCK=true) to test
the auth flow without making real Stytch API calls.

Tests use pytest-subtests to share expensive browser setup across
related assertions, reducing redundant page loads.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/implementation-plans/2026-01-31-test-suite-consolidation/phase_05.md
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.auth.mock import (
    MOCK_VALID_MAGIC_TOKEN,
    MOCK_VALID_SSO_TOKEN,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


class TestLoginPage:
    """Tests for the /login page UI elements and magic link flow.

    Uses subtests to share the single page load across multiple element checks.
    """

    def test_login_page_elements_and_magic_link(
        self, subtests, fresh_page: Page, app_server: str
    ) -> None:
        """Login page UI elements and magic link functionality."""
        fresh_page.goto(f"{app_server}/login")

        # --- Subtest: page renders with required elements ---
        with subtests.test(msg="page_renders_with_elements"):
            expect(fresh_page.get_by_test_id("email-input")).to_be_visible()
            expect(fresh_page.get_by_test_id("send-magic-link-btn")).to_be_visible()
            expect(fresh_page.get_by_test_id("sso-login-btn")).to_be_visible()

        # --- Subtest: magic link send with valid email ---
        with subtests.test(msg="magic_link_send_success"):
            fresh_page.get_by_test_id("email-input").fill("test@example.com")
            fresh_page.get_by_test_id("send-magic-link-btn").click()
            expect(fresh_page.get_by_text("Magic link sent")).to_be_visible()

        # Reload for next test
        fresh_page.goto(f"{app_server}/login")

        # --- Subtest: magic link accepts arbitrary email ---
        with subtests.test(msg="magic_link_arbitrary_email"):
            fresh_page.get_by_test_id("email-input").fill("arbitrary@anywhere.com")
            fresh_page.get_by_test_id("send-magic-link-btn").click()
            expect(fresh_page.get_by_text("Magic link sent")).to_be_visible()


class TestMagicLinkCallback:
    """Tests for the /auth/callback page (magic link authentication).

    Uses subtests to share browser context across callback scenarios.
    """

    def test_callback_token_handling(
        self, subtests, fresh_page: Page, app_server: str
    ) -> None:
        """Callback page handles valid, invalid, and missing tokens."""
        # --- Subtest: valid token authenticates and redirects ---
        with subtests.test(msg="valid_token_redirects"):
            fresh_page.goto(
                f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}"
            )
            expect(fresh_page).to_have_url(f"{app_server}/")

        # Clear session for next test
        fresh_page.goto(f"{app_server}/logout")

        # --- Subtest: invalid token shows error ---
        with subtests.test(msg="invalid_token_shows_error"):
            fresh_page.goto(f"{app_server}/auth/callback?token=bad-token")
            expect(fresh_page.get_by_text("Error: invalid_token")).to_be_visible()
            expect(fresh_page).to_have_url(f"{app_server}/login", timeout=5000)

        # --- Subtest: missing token shows error ---
        with subtests.test(msg="missing_token_shows_error"):
            fresh_page.goto(f"{app_server}/auth/callback")
            expect(
                fresh_page.get_by_text("Invalid or missing token").first
            ).to_be_visible()
            expect(fresh_page).to_have_url(f"{app_server}/login", timeout=5000)


class TestSSOFlow:
    """Tests for SSO authentication flow.

    Uses subtests to share browser context across SSO scenarios.
    """

    def test_sso_authentication_flow(
        self, subtests, fresh_page: Page, app_server: str
    ) -> None:
        """SSO start redirects and callback handles tokens."""
        # --- Subtest: SSO start generates correct redirect ---
        with subtests.test(msg="sso_start_redirects"):
            fresh_page.goto(f"{app_server}/login")

            redirect_url = None

            def capture_redirect(route):
                nonlocal redirect_url
                redirect_url = route.request.url
                route.abort()

            fresh_page.route("**/mock.stytch.com/**", capture_redirect)
            fresh_page.get_by_test_id("sso-login-btn").click()
            fresh_page.wait_for_timeout(200)

            assert redirect_url is not None, "SSO redirect was not triggered"
            assert "mock.stytch.com" in redirect_url
            assert "connection_id=" in redirect_url
            assert "public_token=" in redirect_url

            # Clear the route handler for subsequent tests
            fresh_page.unroute("**/mock.stytch.com/**")

        # --- Subtest: valid SSO token authenticates ---
        with subtests.test(msg="sso_callback_valid_token"):
            fresh_page.goto(
                f"{app_server}/auth/sso/callback?token={MOCK_VALID_SSO_TOKEN}"
            )
            expect(fresh_page).to_have_url(f"{app_server}/")

        # Clear session for next test
        fresh_page.goto(f"{app_server}/logout")

        # --- Subtest: invalid SSO token shows error ---
        with subtests.test(msg="sso_callback_invalid_token"):
            fresh_page.goto(f"{app_server}/auth/sso/callback?token=bad-sso-token")
            expect(fresh_page.get_by_text("invalid_token").first).to_be_visible()
            expect(fresh_page).to_have_url(f"{app_server}/login", timeout=5000)


class TestProtectedPage:
    """Tests for the /protected page authentication requirements.

    Uses subtests to share authenticated session across related checks.
    """

    def test_protected_page_unauthenticated(
        self, fresh_page: Page, app_server: str
    ) -> None:
        """Protected page redirects to login if not authenticated."""
        fresh_page.goto(f"{app_server}/protected")
        expect(fresh_page).to_have_url(f"{app_server}/login")

    def test_protected_page_authenticated_flow(
        self, subtests, fresh_page: Page, app_server: str
    ) -> None:
        """Protected page behaviour when authenticated (user info, logout)."""
        # Authenticate first
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(fresh_page).to_have_url(f"{app_server}/")

        # Navigate to protected page
        fresh_page.goto(f"{app_server}/protected")

        # --- Subtest: shows user info ---
        with subtests.test(msg="shows_user_info"):
            expect(fresh_page.get_by_text("test@example.com")).to_be_visible()
            expect(fresh_page.get_by_text("stytch_member")).to_be_visible()

        # --- Subtest: logout clears session ---
        with subtests.test(msg="logout_clears_session"):
            fresh_page.get_by_test_id("logout-btn").click()
            expect(fresh_page).to_have_url(f"{app_server}/login")

            # Verify session is cleared
            fresh_page.goto(f"{app_server}/protected")
            expect(fresh_page).to_have_url(f"{app_server}/login")


class TestSessionPersistence:
    """Tests for session persistence across page loads and navigation.

    Uses subtests to share authenticated session across persistence checks.
    """

    def test_session_persists(
        self, subtests, fresh_page: Page, app_server: str
    ) -> None:
        """Session persists on refresh and across navigation."""
        # Authenticate first
        fresh_page.goto(f"{app_server}/auth/callback?token={MOCK_VALID_MAGIC_TOKEN}")
        expect(fresh_page).to_have_url(f"{app_server}/")

        # Navigate to protected page
        fresh_page.goto(f"{app_server}/protected")

        # --- Subtest: session persists on refresh ---
        with subtests.test(msg="persists_on_refresh"):
            fresh_page.reload()
            expect(fresh_page).to_have_url(f"{app_server}/protected")
            expect(fresh_page.get_by_text("test@example.com")).to_be_visible()

        # --- Subtest: session persists across navigation ---
        with subtests.test(msg="persists_across_navigation"):
            fresh_page.goto(f"{app_server}/login")
            fresh_page.goto(f"{app_server}/protected")
            expect(fresh_page).to_have_url(f"{app_server}/protected")
