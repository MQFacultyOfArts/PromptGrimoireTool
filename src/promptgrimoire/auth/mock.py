"""Mock auth client for testing.

This module provides a mock implementation of the AuthClientProtocol
that can be used in tests without making real Stytch API calls.

Supports arbitrary users - any email can request a magic link and authenticate.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlencode

from promptgrimoire.auth.models import (
    AuthResult,
    OAuthStartResult,
    SendResult,
    SessionResult,
    SSOStartResult,
)

# Predefined test values for consistent behavior in tests
# These are kept for backwards compatibility with existing tests
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


def _email_to_member_id(email: str) -> str:
    """Generate a deterministic member ID from an email."""
    return f"mock-member-{hashlib.md5(email.encode()).hexdigest()[:8]}"


def _email_to_session_token(email: str) -> str:
    """Generate a deterministic session token from an email."""
    return f"mock-session-{hashlib.md5(email.encode()).hexdigest()[:12]}"


class MockAuthClient:
    """Mock implementation of AuthClientProtocol for testing.

    This client provides predictable responses for testing auth flows
    without making real API calls. Supports arbitrary users.

    Token Formats:
        - "mock-valid-token" - authenticates as last email that requested magic link
        - "mock-token-{email}" - authenticates as specific email
        - "mock-valid-sso-token" - authenticates as SSO user
        - "mock-valid-oauth-token" - authenticates as GitHub user

    Session tokens are email-specific for multi-user testing.
    """

    def __init__(self) -> None:
        """Initialize the mock client."""
        # Track sent magic links for testing
        self._sent_magic_links: list[dict] = []
        # Track pending magic link email (most recent)
        self._pending_email: str | None = None
        # Track active sessions: session_token -> email
        self._active_sessions: dict[str, str] = {}

    async def send_magic_link(
        self,
        email: str,
        organization_id: str,
        callback_url: str,
    ) -> SendResult:
        """Mock sending a magic link email.

        Accepts any email address for testing flexibility.

        Args:
            email: The recipient's email address.
            organization_id: The organization ID.
            callback_url: The callback URL (ignored in mock).

        Returns:
            SendResult - always succeeds for any email.
        """
        # Track the call for testing
        self._sent_magic_links.append(
            {
                "email": email,
                "organization_id": organization_id,
                "callback_url": callback_url,
            }
        )

        # Store pending email for when token is authenticated
        self._pending_email = email

        return SendResult(
            success=True,
            member_id=_email_to_member_id(email),
            member_created=email not in MOCK_VALID_EMAILS,
        )

    async def authenticate_magic_link(self, token: str) -> AuthResult:
        """Mock authenticating a magic link token.

        Args:
            token: The magic link token. Accepts:
                - "mock-valid-token" - uses pending email from send_magic_link
                - "mock-token-{email}" - authenticates as specific email

        Returns:
            AuthResult - success for valid token formats.
        """
        email: str | None = None

        # Check for email-specific token format: mock-token-{email}
        if token.startswith("mock-token-"):
            email = token[len("mock-token-") :]
        elif token == MOCK_VALID_MAGIC_TOKEN:
            # Use pending email from most recent send_magic_link call
            email = self._pending_email or "test@example.com"

        if email:
            session_token = _email_to_session_token(email)
            self._active_sessions[session_token] = email
            return AuthResult(
                success=True,
                session_token=session_token,
                session_jwt=f"mock-jwt-{email}",
                member_id=_email_to_member_id(email),
                organization_id=MOCK_ORG_ID,
                email=email,
                name=email.split("@")[0].replace(".", " ").title(),
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
                name="SSO User",
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
            SessionResult - valid if token is in active sessions or is legacy token.
        """
        # Check active sessions first (from authenticate_magic_link)
        if session_token in self._active_sessions:
            email = self._active_sessions[session_token]
            return SessionResult(
                valid=True,
                member_id=_email_to_member_id(email),
                organization_id=MOCK_ORG_ID,
                email=email,
                name=email.split("@")[0].replace(".", " ").title(),
                roles=["stytch_member"],
            )

        # Legacy support for hardcoded token
        if session_token == MOCK_VALID_SESSION:
            return SessionResult(
                valid=True,
                member_id=MOCK_MEMBER_ID,
                organization_id=MOCK_ORG_ID,
                email="test@example.com",
                name="Test User",
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
        organization_id: str,
        login_redirect_url: str,
    ) -> OAuthStartResult:
        """Mock generating an OAuth start URL.

        Args:
            provider: The OAuth provider (e.g., "github").
            public_token: The public token.
            organization_id: The Stytch organization ID.
            login_redirect_url: The redirect URL after OAuth.

        Returns:
            OAuthStartResult with a mock redirect URL.
        """
        params = {
            "public_token": public_token,
            "organization_id": organization_id,
            "login_redirect_url": login_redirect_url,
            "signup_redirect_url": login_redirect_url,
        }
        redirect_url = (
            f"https://mock.stytch.com/v1/b2b/public/oauth/{provider}/start"
            f"?{urlencode(params)}"
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
                name="GitHub User",
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
