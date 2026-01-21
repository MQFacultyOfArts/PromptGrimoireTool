"""Data models for authentication results.

These dataclasses represent the outcomes of various auth operations,
providing a consistent interface between the real Stytch client and mock.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SendResult:
    """Result of sending a magic link email.

    Attributes:
        success: Whether the email was sent successfully.
        member_id: The Stytch member ID (if successful).
        member_created: True if this was a new member signup.
        error: Error type if the operation failed.
    """

    success: bool
    member_id: str | None = None
    member_created: bool = False
    error: str | None = None


@dataclass(frozen=True)
class AuthResult:
    """Result of authenticating a magic link or SSO token.

    Attributes:
        success: Whether authentication succeeded.
        session_token: The session token for subsequent requests.
        session_jwt: Short-lived JWT for client-side validation.
        member_id: The authenticated member's ID.
        organization_id: The organization the member authenticated into.
        email: The member's email address.
        roles: List of role IDs assigned to the member.
        error: Error type if authentication failed.
    """

    success: bool
    session_token: str | None = None
    session_jwt: str | None = None
    member_id: str | None = None
    organization_id: str | None = None
    email: str | None = None
    roles: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class SessionResult:
    """Result of validating an existing session.

    Attributes:
        valid: Whether the session is still valid.
        member_id: The member ID associated with the session.
        organization_id: The organization ID for the session.
        email: The member's email address.
        roles: List of role IDs from the session.
        error: Error type if validation failed.
    """

    valid: bool
    member_id: str | None = None
    organization_id: str | None = None
    email: str | None = None
    roles: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class SSOStartResult:
    """Result of starting an SSO flow.

    Attributes:
        success: Whether the SSO URL was generated.
        redirect_url: The URL to redirect the user to for SSO.
        error: Error type if the operation failed.
    """

    success: bool
    redirect_url: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class OAuthStartResult:
    """Result of starting an OAuth flow.

    Attributes:
        success: Whether the OAuth URL was generated.
        redirect_url: The URL to redirect the user to for OAuth.
        error: Error type if the operation failed.
    """

    success: bool
    redirect_url: str | None = None
    error: str | None = None
