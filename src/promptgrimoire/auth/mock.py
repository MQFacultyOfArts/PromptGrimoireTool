"""Mock auth client for testing.

This module provides a mock implementation of the AuthClientProtocol
that can be used in tests without making real Stytch API calls.
"""

from __future__ import annotations

from urllib.parse import urlencode

from promptgrimoire.auth.models import (
    AuthResult,
    OAuthStartResult,
    SendResult,
    SessionResult,
    SSOStartResult,
)

# Predefined test values for consistent behavior in tests
MOCK_VALID_EMAILS = frozenset(
    {"test@example.com", "student@uni.edu", "instructor@uni.edu"}
)
MOCK_VALID_MAGIC_TOKEN = "mock-valid-token"
MOCK_VALID_SSO_TOKEN = "mock-valid-sso-token"
MOCK_VALID_OAUTH_TOKEN = "mock-valid-oauth-token"
MOCK_VALID_SESSION = "mock-session-token"

# Test organization and member IDs
MOCK_ORG_ID = "mock-org-123"
MOCK_MEMBER_ID = "mock-member-456"


class MockAuthClient:
    """Mock implementation of AuthClientProtocol for testing.

    This client provides predictable responses for testing auth flows
    without making real API calls. It recognizes specific test values
    and returns appropriate success/failure responses.

    Test Values:
        - Valid emails: test@example.com, student@uni.edu, instructor@uni.edu
        - Valid magic link token: "mock-valid-token"
        - Valid SSO token: "mock-valid-sso-token"
        - Valid session token: "mock-session-token"
    """

    def __init__(self) -> None:
        """Initialize the mock client."""
        # Track sent magic links for testing
        self._sent_magic_links: list[dict] = []

    async def send_magic_link(
        self,
        email: str,
        organization_id: str,
        callback_url: str,
    ) -> SendResult:
        """Mock sending a magic link email.

        Args:
            email: The recipient's email address.
            organization_id: The organization ID.
            callback_url: The callback URL (ignored in mock).

        Returns:
            SendResult - success if email is in MOCK_VALID_EMAILS.
        """
        # Track the call for testing
        self._sent_magic_links.append(
            {
                "email": email,
                "organization_id": organization_id,
                "callback_url": callback_url,
            }
        )

        if email in MOCK_VALID_EMAILS:
            # Determine if this is a "new" user
            is_new = email == "student@uni.edu"
            return SendResult(
                success=True,
                member_id=MOCK_MEMBER_ID,
                member_created=is_new,
            )
        return SendResult(
            success=False,
            error="invalid_email",
        )

    async def authenticate_magic_link(self, token: str) -> AuthResult:
        """Mock authenticating a magic link token.

        Args:
            token: The magic link token.

        Returns:
            AuthResult - success if token equals MOCK_VALID_MAGIC_TOKEN.
        """
        if token == MOCK_VALID_MAGIC_TOKEN:
            return AuthResult(
                success=True,
                session_token=MOCK_VALID_SESSION,
                session_jwt="mock-jwt-token",
                member_id=MOCK_MEMBER_ID,
                organization_id=MOCK_ORG_ID,
                email="test@example.com",
                roles=["stytch_member"],
            )
        return AuthResult(
            success=False,
            error="invalid_token",
        )

    async def authenticate_sso(self, token: str) -> AuthResult:
        """Mock authenticating an SSO token.

        Args:
            token: The SSO callback token.

        Returns:
            AuthResult - success if token equals MOCK_VALID_SSO_TOKEN.
        """
        if token == MOCK_VALID_SSO_TOKEN:
            return AuthResult(
                success=True,
                session_token=MOCK_VALID_SESSION,
                session_jwt="mock-sso-jwt",
                member_id=MOCK_MEMBER_ID,
                organization_id=MOCK_ORG_ID,
                email="aaf-user@uni.edu",
                roles=["stytch_member", "instructor"],
            )
        return AuthResult(
            success=False,
            error="invalid_token",
        )

    async def validate_session(self, session_token: str) -> SessionResult:
        """Mock validating a session token.

        Args:
            session_token: The session token to validate.

        Returns:
            SessionResult - valid if token equals MOCK_VALID_SESSION.
        """
        if session_token == MOCK_VALID_SESSION:
            return SessionResult(
                valid=True,
                member_id=MOCK_MEMBER_ID,
                organization_id=MOCK_ORG_ID,
                email="test@example.com",
                roles=["stytch_member"],
            )
        return SessionResult(
            valid=False,
            error="session_not_found",
        )

    def get_sso_start_url(
        self,
        connection_id: str,
        public_token: str,
    ) -> SSOStartResult:
        """Mock generating an SSO start URL.

        Args:
            connection_id: The SSO connection ID.
            public_token: The public token.

        Returns:
            SSOStartResult with a mock redirect URL.
        """

        # Return a mock URL that can be detected in tests
        params = {
            "connection_id": connection_id,
            "public_token": public_token,
        }
        redirect_url = f"https://mock.stytch.com/v1/b2b/sso/start?{urlencode(params)}"
        return SSOStartResult(
            success=True,
            redirect_url=redirect_url,
        )

    def get_oauth_start_url(
        self,
        provider: str,
        public_token: str,
        discovery_redirect_url: str,
    ) -> OAuthStartResult:
        """Mock generating an OAuth start URL.

        Args:
            provider: The OAuth provider (e.g., "github").
            public_token: The public token.
            discovery_redirect_url: The redirect URL after OAuth.

        Returns:
            OAuthStartResult with a mock redirect URL.
        """
        redirect_url = (
            f"https://mock.stytch.com/v1/b2b/public/oauth/{provider}/discovery/start"
            f"?public_token={public_token}"
            f"&discovery_redirect_url={discovery_redirect_url}"
        )
        return OAuthStartResult(
            success=True,
            redirect_url=redirect_url,
        )

    async def authenticate_oauth(self, token: str) -> AuthResult:
        """Mock authenticating an OAuth token.

        Args:
            token: The OAuth callback token.

        Returns:
            AuthResult - success if token equals MOCK_VALID_OAUTH_TOKEN.
        """
        if token == MOCK_VALID_OAUTH_TOKEN:
            return AuthResult(
                success=True,
                session_token=MOCK_VALID_SESSION,
                session_jwt="mock-oauth-jwt",
                member_id=MOCK_MEMBER_ID,
                organization_id=MOCK_ORG_ID,
                email="github-user@example.com",
                roles=["stytch_member"],
            )
        return AuthResult(
            success=False,
            error="invalid_token",
        )

    # Test helper methods

    def get_sent_magic_links(self) -> list[dict]:
        """Return list of magic links that were 'sent' (for test assertions)."""
        return self._sent_magic_links.copy()

    def clear_sent_magic_links(self) -> None:
        """Clear the list of sent magic links."""
        self._sent_magic_links.clear()
