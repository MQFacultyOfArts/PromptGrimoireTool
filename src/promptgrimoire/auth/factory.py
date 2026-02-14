"""Auth client factory.

Provides a factory function to get the appropriate auth client
based on configuration (real Stytch or mock for testing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from promptgrimoire.auth.protocol import AuthClientProtocol


# Cached mock client instance to preserve session state across requests
_mock_client_instance: AuthClientProtocol | None = None


def get_auth_client() -> AuthClientProtocol:
    """Get the appropriate auth client based on configuration.

    If DEV__AUTH_MOCK=true, returns MockAuthClient (singleton to preserve sessions).
    Otherwise, returns StytchB2BClient with real credentials.

    Returns:
        An auth client implementing AuthClientProtocol.

    Raises:
        ValueError: If stytch.project_id is empty and mock mode is disabled.
    """
    global _mock_client_instance  # noqa: PLW0603
    settings = get_settings()

    if settings.dev.auth_mock:
        if _mock_client_instance is None:
            from promptgrimoire.auth.mock import MockAuthClient

            _mock_client_instance = MockAuthClient()
        return _mock_client_instance

    stytch = settings.stytch
    if not stytch.project_id:
        msg = (
            "STYTCH__PROJECT_ID is required when DEV__AUTH_MOCK is not enabled. "
            "Set STYTCH__PROJECT_ID and STYTCH__SECRET in your .env file."
        )
        raise ValueError(msg)

    from promptgrimoire.auth.client import StytchB2BClient

    return StytchB2BClient(
        project_id=stytch.project_id,
        secret=stytch.secret.get_secret_value(),
    )


def clear_config_cache() -> None:
    """Clear the configuration and mock client caches.

    Useful for testing when you need to reload configuration
    or reset mock client session state.
    """
    global _mock_client_instance  # noqa: PLW0603
    get_settings.cache_clear()
    _mock_client_instance = None
