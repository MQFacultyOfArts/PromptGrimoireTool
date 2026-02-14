"""Authentication module for PromptGrimoire.

Provides Stytch B2B authentication with support for:
- Magic link authentication
- SSO via SAML (AAF Rapid IdP)
- Mock client for testing

Usage:
    from promptgrimoire.auth import get_auth_client

    # Get the configured auth client
    client = get_auth_client()

    # Send a magic link
    result = await client.send_magic_link(
        email="user@example.com",
        organization_id="org-123",
        callback_url="http://localhost:8080/auth/callback",
    )
"""

from promptgrimoire.auth.factory import clear_config_cache, get_auth_client
from promptgrimoire.auth.models import (
    AuthResult,
    SendResult,
    SessionResult,
    SSOStartResult,
)
from promptgrimoire.auth.protocol import AuthClientProtocol

_PRIVILEGED_ROLES = frozenset({"instructor", "stytch_admin"})


def is_privileged_user(auth_user: dict[str, object] | None) -> bool:
    """Check if user has instructor or admin privileges.

    Returns True if the user is an org-level admin or has an instructor/stytch_admin
    role. Returns False for students, tutors, unauthenticated users, or missing data.
    """
    if auth_user is None:
        return False
    if auth_user.get("is_admin") is True:
        return True
    roles = auth_user.get("roles")
    if not isinstance(roles, list):
        return False
    return bool(_PRIVILEGED_ROLES & set(roles))


__all__ = [
    "AuthClientProtocol",
    "AuthResult",
    "SSOStartResult",
    "SendResult",
    "SessionResult",
    "clear_config_cache",
    "get_auth_client",
    "is_privileged_user",
]
