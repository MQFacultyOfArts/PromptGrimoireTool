"""Protocol defining the auth client interface.

Both StytchB2BClient and MockAuthClient implement this protocol,
allowing them to be used interchangeably.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from promptgrimoire.auth.models import (
        AuthResult,
        SendResult,
        SessionResult,
        SSOStartResult,
    )


class AuthClientProtocol(Protocol):
    """Protocol for authentication clients.

    This defines the interface that both the real Stytch client
    and the mock client must implement.
    """

    async def send_magic_link(
        self,
        email: str,
        organization_id: str,
        callback_url: str,
    ) -> SendResult:
        """Send a magic link email to the user.

        Args:
            email: The recipient's email address.
            organization_id: The Stytch organization ID.
            callback_url: URL to redirect to after clicking the link.

        Returns:
            SendResult with success status and member info.
        """
        ...

    async def authenticate_magic_link(self, token: str) -> AuthResult:
        """Authenticate a magic link token.

        Args:
            token: The token from the magic link callback URL.

        Returns:
            AuthResult with session info if successful.
        """
        ...

    async def authenticate_sso(self, token: str) -> AuthResult:
        """Authenticate an SSO token from the IdP callback.

        Args:
            token: The token from the SSO callback URL.

        Returns:
            AuthResult with session info if successful.
        """
        ...

    async def validate_session(self, session_token: str) -> SessionResult:
        """Validate an existing session token.

        Args:
            session_token: The session token to validate.

        Returns:
            SessionResult indicating if the session is valid.
        """
        ...

    def get_sso_start_url(
        self,
        connection_id: str,
        public_token: str,
    ) -> SSOStartResult:
        """Generate the URL to start an SSO flow.

        Args:
            connection_id: The Stytch SSO connection ID.
            public_token: The Stytch public token.

        Returns:
            SSOStartResult with the redirect URL.
        """
        ...
