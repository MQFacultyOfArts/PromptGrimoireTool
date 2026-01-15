"""Stytch B2B client wrapper for authentication.

This module provides a wrapper around the Stytch B2B SDK that implements
the AuthClientProtocol, providing a consistent interface for magic link
and SSO authentication.
"""

from __future__ import annotations

from stytch import B2BClient
from stytch.core.response_base import StytchError

from promptgrimoire.auth.models import (
    AuthResult,
    SendResult,
    SessionResult,
    SSOStartResult,
)

# Stytch API base URLs
STYTCH_TEST_API = "https://test.stytch.com"
STYTCH_LIVE_API = "https://api.stytch.com"


class StytchB2BClient:
    """Wrapper around Stytch B2BClient for magic link and SSO auth.

    This class implements the AuthClientProtocol and provides methods
    for sending magic links, authenticating tokens, and managing sessions.
    """

    def __init__(
        self,
        project_id: str,
        secret: str,
        *,
        environment: str = "test",
    ) -> None:
        """Initialize the Stytch client.

        Args:
            project_id: Stytch project ID.
            secret: Stytch secret key.
            environment: Either "test" or "live".
        """
        self._client = B2BClient(
            project_id=project_id,
            secret=secret,
            environment=environment,
        )
        self._environment = environment

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
        try:
            response = await self._client.magic_links.email.login_or_signup_async(
                organization_id=organization_id,
                email_address=email,
                login_redirect_url=callback_url,
                signup_redirect_url=callback_url,
            )
            return SendResult(
                success=True,
                member_id=response.member_id,
                member_created=response.member_created,
            )
        except StytchError as e:
            return SendResult(
                success=False,
                error=e.details.error_type,
            )

    async def authenticate_magic_link(self, token: str) -> AuthResult:
        """Authenticate a magic link token.

        Args:
            token: The token from the magic link callback URL.

        Returns:
            AuthResult with session info if successful.
        """
        try:
            response = await self._client.magic_links.authenticate_async(
                magic_links_token=token,
                session_duration_minutes=60 * 24 * 7,  # 1 week
            )

            # Check if MFA is required
            if not response.member_authenticated:
                return AuthResult(
                    success=False,
                    error="mfa_required",
                )

            # Roles may be strings or objects depending on SDK version
            raw_roles = response.member_session.roles
            if raw_roles and hasattr(raw_roles[0], "role_id"):
                roles = [role.role_id for role in raw_roles]
            else:
                roles = list(raw_roles) if raw_roles else []

            return AuthResult(
                success=True,
                session_token=response.session_token,
                session_jwt=response.session_jwt,
                member_id=response.member_id,
                organization_id=response.organization_id,
                email=response.member.email_address,
                roles=roles,
            )
        except StytchError as e:
            return AuthResult(
                success=False,
                error=e.details.error_type,
            )

    async def authenticate_sso(self, token: str) -> AuthResult:
        """Authenticate an SSO token from the IdP callback.

        Args:
            token: The token from the SSO callback URL.

        Returns:
            AuthResult with session info if successful.
        """
        try:
            response = await self._client.sso.authenticate_async(
                sso_token=token,
                session_duration_minutes=60 * 24 * 7,  # 1 week
            )

            # Roles may be strings or objects depending on SDK version
            raw_roles = response.member_session.roles
            if raw_roles and hasattr(raw_roles[0], "role_id"):
                roles = [role.role_id for role in raw_roles]
            else:
                roles = list(raw_roles) if raw_roles else []

            return AuthResult(
                success=True,
                session_token=response.session_token,
                session_jwt=response.session_jwt,
                member_id=response.member_id,
                organization_id=response.organization_id,
                email=response.member.email_address,
                roles=roles,
            )
        except StytchError as e:
            return AuthResult(
                success=False,
                error=e.details.error_type,
            )

    async def validate_session(self, session_token: str) -> SessionResult:
        """Validate an existing session token.

        Args:
            session_token: The session token to validate.

        Returns:
            SessionResult indicating if the session is valid.
        """
        try:
            response = await self._client.sessions.authenticate_async(
                session_token=session_token,
            )

            # Roles may be strings or objects depending on SDK version
            raw_roles = response.member_session.roles
            if raw_roles and hasattr(raw_roles[0], "role_id"):
                roles = [role.role_id for role in raw_roles]
            else:
                roles = list(raw_roles) if raw_roles else []

            return SessionResult(
                valid=True,
                member_id=response.member_id,
                organization_id=response.organization_id,
                email=response.member.email_address,
                roles=roles,
            )
        except StytchError as e:
            return SessionResult(
                valid=False,
                error=e.details.error_type,
            )

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
        base_url = STYTCH_TEST_API if self._environment == "test" else STYTCH_LIVE_API
        # Use the public SSO start endpoint - works for both OIDC and SAML
        redirect_url = (
            f"{base_url}/v1/public/sso/start"
            f"?connection_id={connection_id}"
            f"&public_token={public_token}"
        )
        return SSOStartResult(
            success=True,
            redirect_url=redirect_url,
        )
