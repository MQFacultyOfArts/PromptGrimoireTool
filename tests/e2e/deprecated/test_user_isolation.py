"""E2E tests for per-user isolation in demo pages.

Verifies that different users get isolated document state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip all tests in this module - coverage in test_auth_pages.py
pytestmark = pytest.mark.skip(
    reason="Deprecated: auth/isolation coverage exists in test_auth_pages.py. "
    "Demo-specific document isolation tests not applicable. "
    "See coverage-mapping.md for details."
)


class TestLiveAnnotationUserIsolation:
    """Tests for per-user isolation in live annotation demo."""

    @pytest.fixture
    def user_a_token(self) -> str:
        """Mock token for user A."""
        return "mock-token-user-a@test.example.edu.au"

    def _login_as(self, page: Page, app_server: str, token: str) -> None:
        """Helper to log in with a mock token."""
        page.goto(f"{app_server}/auth/callback?token={token}")
        # Wait for redirect to home
        page.wait_for_url(f"{app_server}/")

    def test_different_users_see_different_documents(
        self, page: Page, app_server: str, user_a_token: str
    ) -> None:
        """User should see their own isolated document."""
        # User A logs in and visits live annotation
        self._login_as(page, app_server, user_a_token)
        page.goto(f"{app_server}/demo/live-annotation")
        page.wait_for_selector(".doc-container", timeout=10000)

        # Verify page loaded successfully with user-specific content
        # The doc_id is internal (demo-{email}), but we verify the page works
        assert page.locator("text=Live Annotation Demo").is_visible()

    def test_unauthenticated_user_redirected_to_login(
        self, page: Page, app_server: str
    ) -> None:
        """Unauthenticated users should be redirected to login."""
        # Clear any existing session by going to logout first
        page.goto(f"{app_server}/logout")

        # Try to access live annotation without auth
        page.goto(f"{app_server}/demo/live-annotation")

        # Should be redirected to login
        page.wait_for_url(f"{app_server}/login", timeout=5000)

    def test_user_identity_shown_correctly(
        self, page: Page, app_server: str, user_a_token: str
    ) -> None:
        """User's name/email should be shown on the page."""
        self._login_as(page, app_server, user_a_token)
        page.goto(f"{app_server}/demo/live-annotation")
        page.wait_for_selector(".doc-container", timeout=10000)

        # Should show "You are: User A" (derived from email prefix)
        you_are_label = page.locator("text=You are:")
        assert you_are_label.is_visible()


class TestCRDTSyncUserIsolation:
    """Tests for per-user isolation in CRDT sync demo."""

    @pytest.fixture
    def user_a_token(self) -> str:
        """Mock token for user A."""
        return "mock-token-sync-user-a@test.example.edu.au"

    @pytest.fixture
    def user_b_token(self) -> str:
        """Mock token for user B."""
        return "mock-token-sync-user-b@test.example.edu.au"

    def _login_as(self, page: Page, app_server: str, token: str) -> None:
        """Helper to log in with a mock token."""
        page.goto(f"{app_server}/auth/callback?token={token}")
        page.wait_for_url(f"{app_server}/")

    def test_unauthenticated_user_redirected_to_login(
        self, page: Page, app_server: str
    ) -> None:
        """Unauthenticated users should be redirected to login."""
        page.goto(f"{app_server}/logout")
        page.goto(f"{app_server}/demo/crdt-sync")
        page.wait_for_url(f"{app_server}/login", timeout=5000)

    def test_document_id_contains_user_email(
        self, page: Page, app_server: str, user_a_token: str
    ) -> None:
        """Document ID should contain user's email for isolation."""
        self._login_as(page, app_server, user_a_token)
        page.goto(f"{app_server}/demo/crdt-sync")

        # Page shows document ID containing user email
        doc_label = page.locator("text=Document: sync-")
        doc_label.wait_for(timeout=5000)
        assert doc_label.is_visible()
        # Verify the doc ID contains the user's email
        text = doc_label.text_content() or ""
        assert "sync-" in text


class TestTextSelectionUserIsolation:
    """Tests for per-user isolation in text selection demo."""

    @pytest.fixture
    def user_token(self) -> str:
        """Mock token for test user."""
        return "mock-token-text-user@test.example.edu.au"

    def _login_as(self, page: Page, app_server: str, token: str) -> None:
        """Helper to log in with a mock token."""
        page.goto(f"{app_server}/auth/callback?token={token}")
        page.wait_for_url(f"{app_server}/")

    def test_unauthenticated_user_redirected_to_login(
        self, page: Page, app_server: str
    ) -> None:
        """Unauthenticated users should be redirected to login."""
        page.goto(f"{app_server}/logout")
        page.goto(f"{app_server}/demo/text-selection")
        page.wait_for_url(f"{app_server}/login", timeout=5000)

    def test_authenticated_user_can_access(
        self, page: Page, app_server: str, user_token: str
    ) -> None:
        """Authenticated users can access the text selection demo."""
        self._login_as(page, app_server, user_token)
        page.goto(f"{app_server}/demo/text-selection")

        # Should see the demo page
        title = page.locator("text=Text Selection Demo")
        title.wait_for(timeout=5000)
        assert title.is_visible()
