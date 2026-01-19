"""Authentication module for PromptGrimoire.

Provides Stytch B2B authentication with support for:
- Magic link authentication
- SSO via SAML (AAF Rapid IdP)
- Mock client for testing

Usage:
    from promptgrimoire.auth import get_auth_client, get_config

    # Get the configured auth client
    client = get_auth_client()

    # Send a magic link
    result = await client.send_magic_link(
        email="user@example.com",
        organization_id="org-123",
        callback_url="http://localhost:8080/auth/callback",
    )
"""

from promptgrimoire.auth.config import AuthConfig
from promptgrimoire.auth.factory import clear_config_cache, get_auth_client, get_config
from promptgrimoire.auth.models import (
    AuthResult,
    SendResult,
    SessionResult,
    SSOStartResult,
)
from promptgrimoire.auth.protocol import AuthClientProtocol

__all__ = [
    "AuthClientProtocol",
    "AuthConfig",
    "AuthResult",
    "SSOStartResult",
    "SendResult",
    "SessionResult",
    "clear_config_cache",
    "get_auth_client",
    "get_config",
]
